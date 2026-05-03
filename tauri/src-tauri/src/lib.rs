use std::sync::Mutex;
use tauri::State;

const DEFAULT_MODE: &str = "cloud";
const OLLAMA_HEALTH_URL: &str = "http://localhost:11434/api/tags";

pub type ModeState = Mutex<String>;

#[tauri::command]
pub fn get_mode(state: State<'_, ModeState>) -> String {
    state.lock().unwrap().clone()
}

#[tauri::command]
pub fn set_mode(mode: String, state: State<'_, ModeState>) {
    let mut m = state.lock().unwrap();
    *m = mode;
}

/// Lightweight Ollama reachability probe — called from the frontend to
/// show a "Local model ready / not available" indicator without exposing
/// raw `localhost` requests to the WebView CSP.
#[tauri::command]
pub async fn check_ollama() -> bool {
    reqwest::get(OLLAMA_HEALTH_URL)
        .await
        .map(|r| r.status().is_success())
        .unwrap_or(false)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(ModeState::new(DEFAULT_MODE.to_string()))
        .invoke_handler(tauri::generate_handler![get_mode, set_mode, check_ollama])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
