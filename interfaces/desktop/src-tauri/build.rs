fn main() {
    #[cfg(target_os = "macos")]
    {
        cc::Build::new()
            .file("src/mac_dock.m")
            .compile("mac_dock");
        println!("cargo:rustc-link-lib=framework=AppKit");
    }
    tauri_build::build();
}
