import os
import shutil
import sqlite3
from pathlib import Path

def main():
    root = Path.home() / ".julius" / "music_library" / "Julius Songs"
    db_path = Path.home() / ".julius" / "music.db"

    if not root.exists():
        print(f"Directory {root} does not exist.")
        return

    # Connect to database
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Find all flac files in Julius Songs
    moved_count = 0
    for file_path in list(root.rglob("*.flac")):
        rel = file_path.relative_to(root)
        parts = rel.parts
        # If parts is (artist, playlist, filename)
        if len(parts) == 3:
            artist, playlist, filename = parts
            target_dir = root / playlist
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / filename

            old_str = str(file_path.resolve())
            new_str = str(target_path.resolve())

            if old_str != new_str:
                if target_path.exists():
                    file_path.unlink()
                else:
                    shutil.move(old_str, new_str)
                moved_count += 1

                # Update database
                cursor.execute(
                    "UPDATE music_library SET local_path = ? WHERE local_path = ?",
                    (new_str, old_str)
                )
                cursor.execute(
                    "UPDATE music_job_tracks SET local_path = ? WHERE local_path = ?",
                    (new_str, old_str)
                )

    conn.commit()

    # Clean up empty directories
    removed_dirs = 0
    for dirpath in sorted(list(root.glob("*/*")), key=lambda p: len(str(p)), reverse=True):
        if dirpath.is_dir() and not any(dirpath.iterdir()):
            dirpath.rmdir()
            removed_dirs += 1

    for dirpath in sorted(list(root.glob("*")), key=lambda p: len(str(p)), reverse=True):
        if dirpath.is_dir() and not any(dirpath.iterdir()):
            dirpath.rmdir()
            removed_dirs += 1

    print(f"Completed: moved {moved_count} tracks, cleaned up {removed_dirs} empty directories.")

    # Show final structure
    print("\nFinal Julius Songs folders:")
    for item in sorted(root.iterdir()):
        if item.is_dir():
            track_count = len(list(item.glob("*.flac")))
            subdirs = [s.name for s in item.iterdir() if s.is_dir()]
            print(f"  📁 {item.name}/ ({track_count} tracks, subdirs: {subdirs})")

    conn.close()

if __name__ == "__main__":
    main()
