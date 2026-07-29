use std::env;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode, Stdio};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

const DEFAULT_ENDPOINT: &str = "https://api.brainiall.com/v1/tts/synthesize";
const DEFAULT_TEXT: &str = "Esta frase sintética verifica a saída de áudio em português.";
const MAX_RESPONSE_BYTES: u64 = 50 * 1024 * 1024;
const MAX_ENDPOINT_BYTES: usize = 2_048;
const MAX_API_KEY_BYTES: usize = 4_096;

#[derive(Debug)]
struct Args {
    endpoint: String,
    text: String,
    voice: String,
    speed: f32,
    repeat: u32,
    timeout_ms: u64,
    output_dir: PathBuf,
    keep_audio: bool,
}

#[derive(Debug)]
struct WavInfo {
    audio_format: u16,
    channels: u16,
    sample_rate_hz: u32,
    bits_per_sample: u16,
    data_bytes: u32,
}

#[derive(Debug)]
struct RunResult {
    ordinal: u32,
    http_status: u16,
    time_to_first_byte_ms: f64,
    total_ms: f64,
    wall_ms: u128,
    bytes: u64,
    chars_per_second: f64,
    wav: WavInfo,
    output_path: Option<PathBuf>,
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(message) => {
            eprintln!("error: {message}");
            ExitCode::FAILURE
        }
    }
}

fn run() -> Result<(), String> {
    let args = parse_args(env::args().skip(1))?;
    let api_key = env::var("BRAINIALL_API_KEY").map_err(|_| {
        "BRAINIALL_API_KEY is required and must stay outside source control".to_string()
    })?;
    if api_key.trim().is_empty()
        || api_key.contains(['\n', '\r'])
        || api_key.len() > MAX_API_KEY_BYTES
    {
        return Err("BRAINIALL_API_KEY is empty, multiline, or too long".to_string());
    }

    fs::create_dir_all(&args.output_dir)
        .map_err(|error| format!("cannot create output directory: {error}"))?;

    let binary_bytes = env::current_exe()
        .ok()
        .and_then(|path| fs::metadata(path).ok())
        .map(|metadata| metadata.len())
        .unwrap_or(0);

    let mut results = Vec::with_capacity(args.repeat as usize);
    for ordinal in 1..=args.repeat {
        results.push(run_once(&args, &api_key, ordinal)?);
    }

    print_result_json(&args, binary_bytes, &results);
    Ok(())
}

fn parse_args<I>(mut values: I) -> Result<Args, String>
where
    I: Iterator<Item = String>,
{
    let mut args = Args {
        endpoint: DEFAULT_ENDPOINT.to_string(),
        text: DEFAULT_TEXT.to_string(),
        voice: "pf_dora".to_string(),
        speed: 1.0,
        repeat: 2,
        timeout_ms: 30_000,
        output_dir: PathBuf::from("results"),
        keep_audio: false,
    };

    while let Some(flag) = values.next() {
        match flag.as_str() {
            "--endpoint" => args.endpoint = next_value(&mut values, &flag)?,
            "--text" => args.text = next_value(&mut values, &flag)?,
            "--voice" => args.voice = next_value(&mut values, &flag)?,
            "--speed" => {
                args.speed = next_value(&mut values, &flag)?
                    .parse()
                    .map_err(|_| "--speed must be a number".to_string())?;
            }
            "--repeat" => {
                args.repeat = next_value(&mut values, &flag)?
                    .parse()
                    .map_err(|_| "--repeat must be an integer".to_string())?;
            }
            "--timeout-ms" => {
                args.timeout_ms = next_value(&mut values, &flag)?
                    .parse()
                    .map_err(|_| "--timeout-ms must be an integer".to_string())?;
            }
            "--output-dir" => args.output_dir = PathBuf::from(next_value(&mut values, &flag)?),
            "--keep-audio" => args.keep_audio = true,
            "--help" | "-h" => {
                println!(
                    "brainiall-tts-process-benchmark\n\n\
                     --text TEXT          synthetic or authorized text\n\
                     --voice ID           default: pf_dora\n\
                     --speed NUMBER       0.5 to 2.0\n\
                     --repeat N           1 to 10; default: 2\n\
                     --timeout-ms N       hard child-process timeout\n\
                     --endpoint URL       default: production Brainiall TTS\n\
                     --output-dir PATH    temporary/result directory\n\
                     --keep-audio         retain validated WAV outputs"
                );
                std::process::exit(0);
            }
            _ => return Err(format!("unknown argument: {flag}")),
        }
    }

    if args.text.is_empty() || args.text.chars().count() > 5_000 {
        return Err("--text must contain 1 to 5000 characters".to_string());
    }
    if args.voice.is_empty() || args.voice.contains(['\n', '\r']) {
        return Err("--voice must be non-empty and single-line".to_string());
    }
    if !(0.5..=2.0).contains(&args.speed) {
        return Err("--speed must be between 0.5 and 2.0".to_string());
    }
    if !(1..=10).contains(&args.repeat) {
        return Err("--repeat must be between 1 and 10".to_string());
    }
    if !(100..=300_000).contains(&args.timeout_ms) {
        return Err("--timeout-ms must be between 100 and 300000".to_string());
    }
    if !endpoint_is_allowed(&args.endpoint) {
        return Err("--endpoint must be api.brainiall.com over HTTPS or loopback HTTP for an offline fixture".to_string());
    }

    Ok(args)
}

fn endpoint_is_allowed(endpoint: &str) -> bool {
    if endpoint.len() > MAX_ENDPOINT_BYTES || endpoint.contains(['\n', '\r']) {
        return false;
    }

    if let Some(path) = endpoint.strip_prefix("https://api.brainiall.com") {
        return path.starts_with('/');
    }

    let Some(authority_and_path) = endpoint.strip_prefix("http://127.0.0.1") else {
        return false;
    };
    if authority_and_path.starts_with('/') {
        return true;
    }

    let Some(port_and_path) = authority_and_path.strip_prefix(':') else {
        return false;
    };
    let Some((port, _path)) = port_and_path.split_once('/') else {
        return false;
    };
    !port.is_empty()
        && port.bytes().all(|byte| byte.is_ascii_digit())
        && port.parse::<u16>().is_ok_and(|value| value > 0)
}

fn next_value<I>(values: &mut I, flag: &str) -> Result<String, String>
where
    I: Iterator<Item = String>,
{
    values
        .next()
        .ok_or_else(|| format!("missing value after {flag}"))
}

fn run_once(args: &Args, api_key: &str, ordinal: u32) -> Result<RunResult, String> {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|error| format!("clock error: {error}"))?
        .as_nanos();
    let work_dir = args.output_dir.join(format!(
        ".brainiall-tts-{}-{nonce}-{ordinal}",
        std::process::id()
    ));
    fs::create_dir(&work_dir).map_err(|error| format!("cannot create work directory: {error}"))?;
    restrict_permissions(&work_dir, true)?;

    let body_path = work_dir.join("request.json");
    let wav_path = work_dir.join("speech.wav");
    let body = format!(
        "{{\"text\":\"{}\",\"voice\":\"{}\",\"speed\":{}}}",
        json_escape(&args.text),
        json_escape(&args.voice),
        args.speed
    );
    write_private_file(&body_path, body.as_bytes())
        .map_err(|error| cleanup_error(&work_dir, error))?;

    let config = format!(
        "url = \"{}\"\nrequest = \"POST\"\nheader = \"Authorization: Bearer {}\"\nheader = \"Content-Type: application/json\"\n",
        curl_config_escape(&args.endpoint),
        curl_config_escape(api_key)
    );

    let started = Instant::now();
    let mut child = Command::new("curl")
        .arg("-q")
        .arg("--silent")
        .arg("--show-error")
        .arg("--fail-with-body")
        .arg("--max-filesize")
        .arg(MAX_RESPONSE_BYTES.to_string())
        .arg("--config")
        .arg("-")
        .arg("--data-binary")
        .arg(format!("@{}", body_path.display()))
        .arg("--output")
        .arg(&wav_path)
        .arg("--write-out")
        .arg("%{http_code}\t%{time_starttransfer}\t%{time_total}\t%{size_download}")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .env_remove("BRAINIALL_API_KEY")
        .spawn()
        .map_err(|error| cleanup_error(&work_dir, format!("cannot start curl: {error}")))?;

    if let Some(mut stdin) = child.stdin.take() {
        if let Err(error) = stdin.write_all(config.as_bytes()) {
            let _ = child.kill();
            let _ = child.wait();
            return Err(cleanup_error(
                &work_dir,
                format!("cannot configure curl: {error}"),
            ));
        }
    }

    let timeout = Duration::from_millis(args.timeout_ms);
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break status,
            Ok(None) if started.elapsed() < timeout => thread::sleep(Duration::from_millis(20)),
            Ok(None) => {
                let _ = child.kill();
                let _ = child.wait();
                let _ = fs::remove_dir_all(&work_dir);
                return Err(format!(
                    "run {ordinal} exceeded {} ms; curl was killed and reaped",
                    args.timeout_ms
                ));
            }
            Err(error) => {
                let _ = child.kill();
                let _ = child.wait();
                let _ = fs::remove_dir_all(&work_dir);
                return Err(format!("cannot poll curl lifecycle: {error}"));
            }
        }
    };
    let wall_ms = started.elapsed().as_millis();

    let mut stdout = String::new();
    if let Some(mut pipe) = child.stdout.take() {
        pipe.read_to_string(&mut stdout).map_err(|error| {
            cleanup_error(&work_dir, format!("cannot read curl metrics: {error}"))
        })?;
    }
    let mut stderr = String::new();
    if let Some(mut pipe) = child.stderr.take() {
        pipe.read_to_string(&mut stderr).map_err(|error| {
            cleanup_error(&work_dir, format!("cannot read curl error: {error}"))
        })?;
    }

    if !status.success() {
        let _ = fs::remove_dir_all(&work_dir);
        return Err(format!(
            "run {ordinal} failed at the HTTPS boundary (curl exit {:?}): {}",
            status.code(),
            sanitize_error(&stderr, api_key)
        ));
    }

    let metrics: Vec<&str> = stdout.trim().split('\t').collect();
    if metrics.len() != 4 {
        return Err(cleanup_error(
            &work_dir,
            format!("run {ordinal} returned malformed curl metrics"),
        ));
    }
    let http_status = metrics[0]
        .parse::<u16>()
        .map_err(|_| cleanup_error(&work_dir, "invalid HTTP status".to_string()))?;
    if http_status != 200 {
        return Err(cleanup_error(
            &work_dir,
            format!("run {ordinal} returned HTTP {http_status}"),
        ));
    }
    let ttfb_seconds = parse_metric(metrics[1], "time_starttransfer", &work_dir)?;
    let total_seconds = parse_metric(metrics[2], "time_total", &work_dir)?;
    let bytes = metrics[3]
        .parse::<u64>()
        .map_err(|_| cleanup_error(&work_dir, "invalid size_download".to_string()))?;

    let wav = parse_wav_file(&wav_path).map_err(|message| cleanup_error(&work_dir, message))?;
    let final_path = if args.keep_audio {
        let destination = args.output_dir.join(format!("run-{ordinal}.wav"));
        persist_private_file_exclusive(&wav_path, &destination)
            .map_err(|error| cleanup_error(&work_dir, error))?;
        Some(destination)
    } else {
        None
    };
    fs::remove_dir_all(&work_dir)
        .map_err(|error| format!("validated run but could not clean temporary files: {error}"))?;

    Ok(RunResult {
        ordinal,
        http_status,
        time_to_first_byte_ms: ttfb_seconds * 1_000.0,
        total_ms: total_seconds * 1_000.0,
        wall_ms,
        bytes,
        chars_per_second: args.text.chars().count() as f64 / total_seconds.max(0.000_001),
        wav,
        output_path: final_path,
    })
}

fn parse_metric(raw: &str, name: &str, work_dir: &Path) -> Result<f64, String> {
    raw.parse::<f64>()
        .map_err(|_| cleanup_error(work_dir, format!("invalid {name}")))
}

fn write_private_file(path: &Path, contents: &[u8]) -> Result<(), String> {
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options
        .open(path)
        .map_err(|error| format!("cannot create private request file: {error}"))?;
    file.write_all(contents)
        .map_err(|error| format!("cannot write private request file: {error}"))
}

fn persist_private_file_exclusive(source: &Path, destination: &Path) -> Result<(), String> {
    let mut source_file = File::open(source)
        .map_err(|error| format!("cannot open validated audio for retention: {error}"))?;
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut destination_file = options
        .open(destination)
        .map_err(|error| format!("cannot retain audio without overwriting a file: {error}"))?;
    if let Err(error) = std::io::copy(&mut source_file, &mut destination_file) {
        drop(destination_file);
        let _ = fs::remove_file(destination);
        return Err(format!("cannot retain validated audio: {error}"));
    }
    destination_file
        .sync_all()
        .map_err(|error| format!("cannot sync retained audio: {error}"))?;
    Ok(())
}

fn restrict_permissions(path: &Path, directory: bool) -> Result<(), String> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mode = if directory { 0o700 } else { 0o600 };
        fs::set_permissions(path, fs::Permissions::from_mode(mode))
            .map_err(|error| format!("cannot restrict permissions: {error}"))?;
    }
    Ok(())
}

fn parse_wav_file(path: &Path) -> Result<WavInfo, String> {
    let size = fs::metadata(path)
        .map_err(|error| format!("cannot inspect WAV output: {error}"))?
        .len();
    if size > MAX_RESPONSE_BYTES {
        return Err(format!(
            "WAV output exceeds the {} byte safety limit",
            MAX_RESPONSE_BYTES
        ));
    }
    let mut bytes = Vec::new();
    File::open(path)
        .and_then(|mut file| file.read_to_end(&mut bytes))
        .map_err(|error| format!("cannot read WAV output: {error}"))?;
    parse_wav(&bytes)
}

fn parse_wav(bytes: &[u8]) -> Result<WavInfo, String> {
    if bytes.len() < 12 || &bytes[0..4] != b"RIFF" || &bytes[8..12] != b"WAVE" {
        return Err("response is not a RIFF/WAVE file".to_string());
    }
    let declared_riff_bytes = u32::from_le_bytes(bytes[4..8].try_into().unwrap()) as usize + 8;
    if declared_riff_bytes != bytes.len() {
        return Err("RIFF length does not match the file length".to_string());
    }

    let mut offset = 12usize;
    let mut format = None;
    let mut data_bytes = None;
    while offset + 8 <= bytes.len() {
        let id = &bytes[offset..offset + 4];
        let size = u32::from_le_bytes(bytes[offset + 4..offset + 8].try_into().unwrap()) as usize;
        let start = offset + 8;
        let end = start
            .checked_add(size)
            .ok_or_else(|| "WAV chunk length overflow".to_string())?;
        if end > bytes.len() {
            return Err("WAV chunk exceeds file length".to_string());
        }
        if id == b"fmt " {
            if size < 16 {
                return Err("WAV fmt chunk is too short".to_string());
            }
            format = Some((
                u16::from_le_bytes(bytes[start..start + 2].try_into().unwrap()),
                u16::from_le_bytes(bytes[start + 2..start + 4].try_into().unwrap()),
                u32::from_le_bytes(bytes[start + 4..start + 8].try_into().unwrap()),
                u32::from_le_bytes(bytes[start + 8..start + 12].try_into().unwrap()),
                u16::from_le_bytes(bytes[start + 12..start + 14].try_into().unwrap()),
                u16::from_le_bytes(bytes[start + 14..start + 16].try_into().unwrap()),
            ));
        } else if id == b"data" {
            data_bytes = Some(size as u32);
        }
        offset = end
            .checked_add(size % 2)
            .ok_or_else(|| "WAV padding length overflow".to_string())?;
        if offset > bytes.len() {
            return Err("WAV chunk padding exceeds file length".to_string());
        }
    }
    if offset != bytes.len() {
        return Err("WAV file ends with an incomplete chunk".to_string());
    }

    let (audio_format, channels, sample_rate_hz, byte_rate, block_align, bits_per_sample) =
        format.ok_or_else(|| "WAV fmt chunk is missing".to_string())?;
    let data_bytes = data_bytes.ok_or_else(|| "WAV data chunk is missing".to_string())?;
    if audio_format != 1
        || channels != 1
        || sample_rate_hz != 24_000
        || byte_rate != 48_000
        || block_align != 2
        || bits_per_sample != 16
    {
        return Err(format!(
            "unexpected WAV format: format={audio_format}, channels={channels}, sample_rate={sample_rate_hz}, byte_rate={byte_rate}, block_align={block_align}, bits={bits_per_sample}"
        ));
    }
    if data_bytes == 0 || data_bytes % u32::from(block_align) != 0 {
        return Err("WAV data chunk is empty or not frame-aligned".to_string());
    }

    Ok(WavInfo {
        audio_format,
        channels,
        sample_rate_hz,
        bits_per_sample,
        data_bytes,
    })
}

fn json_escape(value: &str) -> String {
    let mut escaped = String::with_capacity(value.len());
    for ch in value.chars() {
        match ch {
            '"' => escaped.push_str("\\\""),
            '\\' => escaped.push_str("\\\\"),
            '\n' => escaped.push_str("\\n"),
            '\r' => escaped.push_str("\\r"),
            '\t' => escaped.push_str("\\t"),
            ch if ch <= '\u{1f}' => escaped.push_str(&format!("\\u{:04x}", ch as u32)),
            ch => escaped.push(ch),
        }
    }
    escaped
}

fn curl_config_escape(value: &str) -> String {
    value.replace('\\', "\\\\").replace('"', "\\\"")
}

fn sanitize_error(value: &str, secret: &str) -> String {
    let redacted = value.replace(secret, "[REDACTED]");
    let trimmed = redacted.trim().replace(['\n', '\r'], " ");
    if trimmed.chars().count() > 240 {
        format!("{}…", trimmed.chars().take(240).collect::<String>())
    } else if trimmed.is_empty() {
        "no diagnostic body".to_string()
    } else {
        trimmed
    }
}

fn cleanup_error(work_dir: &Path, message: String) -> String {
    let _ = fs::remove_dir_all(work_dir);
    message
}

fn print_result_json(args: &Args, binary_bytes: u64, results: &[RunResult]) {
    println!("{{");
    println!("  \"schemaVersion\": 1,");
    println!("  \"candidate\": \"Brainiall hosted TTS over a Rust-owned curl process\",");
    println!("  \"endpoint\": \"{}\",", json_escape(&args.endpoint));
    println!("  \"voice\": \"{}\",", json_escape(&args.voice));
    println!("  \"inputCharacters\": {},", args.text.chars().count());
    println!("  \"repeat\": {},", args.repeat);
    println!("  \"hardTimeoutMs\": {},", args.timeout_ms);
    println!("  \"localModelDownloadBytes\": 0,");
    println!("  \"executableBytes\": {binary_bytes},");
    println!("  \"secretInProcessArguments\": false,");
    println!("  \"runs\": [");
    for (index, result) in results.iter().enumerate() {
        println!("    {{");
        println!("      \"ordinal\": {},", result.ordinal);
        println!(
            "      \"sequence\": \"{}\",",
            if index == 0 {
                "first-process-observation"
            } else {
                "repeat-process-observation"
            }
        );
        println!("      \"httpStatus\": {},", result.http_status);
        println!(
            "      \"timeToFirstByteMs\": {:.3},",
            result.time_to_first_byte_ms
        );
        println!("      \"totalMs\": {:.3},", result.total_ms);
        println!("      \"parentWallMs\": {},", result.wall_ms);
        println!("      \"downloadBytes\": {},", result.bytes);
        println!(
            "      \"inputCharactersPerSecond\": {:.3},",
            result.chars_per_second
        );
        println!("      \"wav\": {{\"audioFormat\": {}, \"channels\": {}, \"sampleRateHz\": {}, \"bitsPerSample\": {}, \"dataBytes\": {}}},", result.wav.audio_format, result.wav.channels, result.wav.sample_rate_hz, result.wav.bits_per_sample, result.wav.data_bytes);
        match &result.output_path {
            Some(path) => println!(
                "      \"retainedOutput\": \"{}\"",
                json_escape(&path.display().to_string())
            ),
            None => println!("      \"retainedOutput\": null"),
        }
        println!(
            "    }}{}",
            if index + 1 == results.len() { "" } else { "," }
        );
    }
    println!("  ],");
    println!("  \"observedClaimsOnly\": true,");
    println!("  \"notProven\": [\"backend cold/warm latency\", \"streaming\", \"chunk-level backpressure\", \"production p95\", \"all voices\", \"third-party integration\", \"buyer adoption\", \"reconciled revenue\"]");
    println!("}}");
}

#[cfg(test)]
mod tests {
    use super::{endpoint_is_allowed, json_escape, parse_wav, sanitize_error};

    fn pcm_wav(data: &[u8]) -> Vec<u8> {
        let mut wav = Vec::new();
        wav.extend_from_slice(b"RIFF");
        wav.extend_from_slice(&(36u32 + data.len() as u32).to_le_bytes());
        wav.extend_from_slice(b"WAVEfmt ");
        wav.extend_from_slice(&16u32.to_le_bytes());
        wav.extend_from_slice(&1u16.to_le_bytes());
        wav.extend_from_slice(&1u16.to_le_bytes());
        wav.extend_from_slice(&24_000u32.to_le_bytes());
        wav.extend_from_slice(&48_000u32.to_le_bytes());
        wav.extend_from_slice(&2u16.to_le_bytes());
        wav.extend_from_slice(&16u16.to_le_bytes());
        wav.extend_from_slice(b"data");
        wav.extend_from_slice(&(data.len() as u32).to_le_bytes());
        wav.extend_from_slice(data);
        wav
    }

    #[test]
    fn escapes_json_without_losing_unicode() {
        assert_eq!(json_escape("Olá\n\"voz\"\\fim"), "Olá\\n\\\"voz\\\"\\\\fim");
    }

    #[test]
    fn accepts_expected_pcm_wav() {
        let parsed = parse_wav(&pcm_wav(&[0, 0, 1, 0])).unwrap();
        assert_eq!(parsed.channels, 1);
        assert_eq!(parsed.sample_rate_hz, 24_000);
        assert_eq!(parsed.bits_per_sample, 16);
        assert_eq!(parsed.data_bytes, 4);
    }

    #[test]
    fn rejects_non_wav_payload() {
        assert!(parse_wav(b"not a wave file").is_err());
    }

    #[test]
    fn rejects_unexpected_sample_rate() {
        let mut wav = pcm_wav(&[0, 0]);
        wav[24..28].copy_from_slice(&16_000u32.to_le_bytes());
        assert!(parse_wav(&wav).is_err());
    }

    #[test]
    fn rejects_mismatched_riff_length_and_odd_pcm_frames() {
        let mut wrong_length = pcm_wav(&[0, 0]);
        wrong_length.extend_from_slice(&[0, 0]);
        assert!(parse_wav(&wrong_length).is_err());

        let odd_frame = pcm_wav(&[0]);
        assert!(parse_wav(&odd_frame).is_err());
    }

    #[test]
    fn accepts_only_structural_production_or_loopback_endpoints() {
        assert!(endpoint_is_allowed(
            "https://api.brainiall.com/v1/tts/synthesize"
        ));
        assert!(endpoint_is_allowed("http://127.0.0.1/fixture"));
        assert!(endpoint_is_allowed("http://127.0.0.1:8080/fixture"));
        assert!(!endpoint_is_allowed(
            "http://127.0.0.1@attacker.example/fixture"
        ));
        assert!(!endpoint_is_allowed(
            "http://127.0.0.1.evil.example/fixture"
        ));
        assert!(!endpoint_is_allowed(
            "https://api.brainiall.com.evil.example/fixture"
        ));
        assert!(!endpoint_is_allowed("http://127.0.0.1:80@evil/fixture"));
    }

    #[test]
    fn redacts_the_exact_secret_before_returning_curl_errors() {
        let sanitized = sanitize_error("trace: Bearer owner-secret-token", "owner-secret-token");
        assert_eq!(sanitized, "trace: Bearer [REDACTED]");
    }
}
