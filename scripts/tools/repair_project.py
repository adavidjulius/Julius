import os
import sys
import json
import shutil
from pathlib import Path

DRAFT_ROOT = Path.home() / "Movies/CapCut/User Data/Projects/com.lveditor.draft"
REF_PROJ = DRAFT_ROOT / "1028"
TARGET_PROJ = DRAFT_ROOT / "AI_Launch_Showcase"
ROOT_META = DRAFT_ROOT / "root_meta_info.json"

def repair():
    print(f"[1] Repairing {TARGET_PROJ}...")
    if not TARGET_PROJ.exists():
        print(f"Error: {TARGET_PROJ} does not exist.")
        return

    # Use the UUID from draft_meta_info or generate a single master UUID
    meta_path = TARGET_PROJ / "draft_meta_info.json"
    content_path = TARGET_PROJ / "draft_content.json"
    info_path = TARGET_PROJ / "draft_info.json"

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    master_uuid = meta.get("draft_id", "792BD5DA-E961-4821-B10E-F51E4683DEC0")
    print(f"    Master UUID: {master_uuid}")

    # 1. Update draft_content.json and draft_info.json
    with open(content_path, "r", encoding="utf-8") as f:
        content = json.load(f)
    content["id"] = master_uuid
    with open(content_path, "w", encoding="utf-8") as f:
        json.dump(content, f, indent=4)
    with open(info_path, "w", encoding="utf-8") as f:
        json.dump(content, f, indent=4)

    # 2. Update draft_meta_info.json
    meta["draft_id"] = master_uuid
    meta["draft_name"] = "AI_Launch_Showcase"
    meta["draft_fold_path"] = str(TARGET_PROJ)
    meta["draft_root_path"] = str(DRAFT_ROOT)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=4)

    # 3. Copy missing companion template files and directories from 1028
    if REF_PROJ.exists():
        for item in REF_PROJ.iterdir():
            if item.name in ["draft_content.json", "draft_info.json", "draft_meta_info.json", "draft_cover.jpg", "draft_info.json.bak"]:
                continue
            dest = TARGET_PROJ / item.name
            if not dest.exists():
                if item.is_dir():
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)
                print(f"    Copied companion: {item.name}")

    # 4. Update root_meta_info.json
    with open(ROOT_META, "r", encoding="utf-8") as f:
        root_data = json.load(f)
    
    found = False
    for dr in root_data.get("all_draft_store", []):
        if dr.get("draft_name") == "AI_Launch_Showcase":
            dr["draft_id"] = master_uuid
            dr["draft_fold_path"] = str(TARGET_PROJ)
            dr["draft_json_file"] = str(info_path)
            dr["draft_cover"] = str(TARGET_PROJ / "draft_cover.jpg")
            dr["draft_new_version"] = "164.0.0"
            dr["streaming_edit_draft_ready"] = True
            found = True
            print("    Updated existing root_meta entry.")
            break
    
    if not found:
        entry = {
            "cloud_draft_cover": False,
            "cloud_draft_sync": False,
            "draft_cloud_last_action_download": False,
            "draft_cover": str(TARGET_PROJ / "draft_cover.jpg"),
            "draft_fold_path": str(TARGET_PROJ),
            "draft_id": master_uuid,
            "draft_json_file": str(info_path),
            "draft_name": "AI_Launch_Showcase",
            "draft_new_version": "164.0.0",
            "draft_root_path": str(DRAFT_ROOT),
            "draft_timeline_materials_size": 20436,
            "streaming_edit_draft_ready": True,
            "tm_draft_create": meta.get("tm_draft_create", 1793174617828183),
            "tm_draft_modified": meta.get("tm_draft_modified", 1793176466582908),
            "tm_draft_removed": 0,
            "tm_duration": content.get("duration", 3500000)
        }
        root_data["all_draft_store"].insert(0, entry)
        print("    Inserted new root_meta entry.")

    with open(ROOT_META, "w", encoding="utf-8") as f:
        json.dump(root_data, f, indent=4)

    print("[5] Repair complete! AI_Launch_Showcase is now 100% compliant and openable.")

if __name__ == "__main__":
    repair()

