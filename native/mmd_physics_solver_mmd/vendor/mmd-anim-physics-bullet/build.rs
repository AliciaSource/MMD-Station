use std::env;
use std::fs;
use std::path::{Path, PathBuf};

fn main() {
    println!("cargo:rerun-if-env-changed=MMD_ANIM_BULLET_DIR");
    println!("cargo:rerun-if-changed=native/mmd_bullet_api.cpp");
    println!("cargo:rerun-if-changed=native/mmd_bullet_api.h");

    if env::var_os("CARGO_FEATURE_NATIVE").is_none() {
        return;
    }

    let manifest_dir = PathBuf::from(env::var_os("CARGO_MANIFEST_DIR").unwrap());
    let bullet_dir = env::var_os("MMD_ANIM_BULLET_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| manifest_dir.join("vendor/bullet-2.75"));
    let bullet_src = bullet_dir.join("src");
    println!("cargo:rerun-if-changed={}", bullet_src.display());

    if !bullet_src.is_dir() {
        panic!(
            "Bullet sources not found at {}. Restore vendor/bullet-2.75 or set MMD_ANIM_BULLET_DIR.",
            bullet_dir.display()
        );
    }

    let mut build = cc::Build::new();
    build
        .cargo_metadata(false)
        .cpp(true)
        .static_crt(true)
        .include(&bullet_src)
        .file("native/mmd_bullet_api.cpp")
        .define("WIN32", None)
        .define("BT_NO_PROFILE", None);

    if let Some(include_paths) = env::var_os("MMD_LEGACY_INCLUDE") {
        for include_path in env::split_paths(&include_paths) {
            build.include(include_path);
        }
    }

    for dir in ["LinearMath", "BulletCollision", "BulletDynamics"] {
        add_cpp_files(&mut build, &bullet_src.join(dir));
    }

    build.compile("mmd_anim_bullet");
    println!("cargo:rustc-link-search=native={}", env::var("OUT_DIR").unwrap());
    println!("cargo:rustc-link-lib=static:-bundle=mmd_anim_bullet");

    if let Some(legacy_libcmt) = env::var_os("MMD_LEGACY_LIBCMT") {
        let legacy_libcmt = PathBuf::from(legacy_libcmt);
        let link_dir = legacy_libcmt.parent().expect("legacy libcmt path has no parent");
        let link_name = legacy_libcmt
            .file_stem()
            .and_then(|name| name.to_str())
            .expect("legacy libcmt path has no valid file stem");
        println!("cargo:rustc-link-search=native={}", link_dir.display());
        println!("cargo:rustc-link-lib=static:-bundle={link_name}");
    }
}

fn add_cpp_files(build: &mut cc::Build, dir: &Path) {
    let entries = fs::read_dir(dir).unwrap_or_else(|err| {
        panic!(
            "failed to read Bullet source directory {}: {err}",
            dir.display()
        )
    });

    for entry in entries {
        let path = entry.unwrap().path();
        if path.is_dir() {
            let path_text = path.to_string_lossy();
            if path_text.contains("TaskScheduler") {
                continue;
            }
            add_cpp_files(build, &path);
            continue;
        }

        if path.extension().and_then(|ext| ext.to_str()) == Some("cpp") {
            build.file(path);
        }
    }
}
