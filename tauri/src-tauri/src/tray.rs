use tauri::image::Image;
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{App, Manager};

use crate::ModeState;

pub fn setup_tray(app: &App) -> Result<(), Box<dyn std::error::Error>> {
    let mode = app
        .state::<ModeState>()
        .lock()
        .map(|m| m.clone())
        .unwrap_or_else(|_| "cloud".to_string());

    let menu = build_menu(app, &mode)?;
    let tray_icon = Image::from_bytes(include_bytes!("../icons/tray-icon.png"))?;

    let _tray = TrayIconBuilder::with_id("main-tray")
        .icon(tray_icon)
        .icon_as_template(true)
        .tooltip("ChatRAG")
        .menu(&menu)
        .show_menu_on_left_click(true)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "quit" => {
                app.exit(0);
            }
            "toggle_mode" => {
                let state = app.state::<ModeState>();
                let new_mode = {
                    let mut m = state.lock().unwrap();
                    let next = if m.as_str() == "cloud" { "local" } else { "cloud" };
                    *m = next.to_string();
                    next.to_string()
                };
                // Rebuild the menu so the displayed mode and toggle label update immediately.
                match build_menu(app, &new_mode) {
                    Ok(updated_menu) => {
                        if let Some(tray) = app.tray_by_id("main-tray") {
                            if let Err(e) = tray.set_menu(Some(updated_menu)) {
                                eprintln!("[tray] Failed to update menu after mode toggle: {e}");
                            }
                        }
                    }
                    Err(e) => {
                        eprintln!("[tray] Failed to rebuild menu: {e}");
                    }
                }
            }
            _ => {}
        })
        .build(app)?;

    Ok(())
}

fn format_mode_label(mode: &str) -> String {
    if mode == "local" {
        "Mode: Local 🖥".to_string()
    } else {
        "Mode: Cloud ☁️".to_string()
    }
}

fn format_toggle_label(mode: &str) -> String {
    if mode == "local" {
        "Switch to Cloud ☁️".to_string()
    } else {
        "Switch to Local 🖥".to_string()
    }
}

fn build_menu(
    app: &impl tauri::Manager<tauri::Wry>,
    mode: &str,
) -> Result<Menu<tauri::Wry>, Box<dyn std::error::Error>> {
    let status = MenuItem::with_id(app, "status", "● Running", false, None::<&str>)?;
    let mode_item = MenuItem::with_id(app, "mode", &format_mode_label(mode), false, None::<&str>)?;
    let mode_separator = PredefinedMenuItem::separator(app)?;
    let toggle = MenuItem::with_id(app, "toggle_mode", &format_toggle_label(mode), true, None::<&str>)?;
    let quit_separator = PredefinedMenuItem::separator(app)?;
    let quit = MenuItem::with_id(app, "quit", "Quit ChatRAG", true, None::<&str>)?;

    Ok(Menu::with_items(
        app,
        &[&status, &mode_item, &mode_separator, &toggle, &quit_separator, &quit],
    )?)
}
