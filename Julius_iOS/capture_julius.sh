#!/bin/bash
OUTPUT="${1:-/tmp/julius_live_window.png}"
WIN_ID=$(swift -e '
import Foundation
import CoreGraphics
let list = CGWindowListCopyWindowInfo(.optionAll, kCGNullWindowID) as! [[String: Any]]
for w in list {
    if let owner = w[kCGWindowOwnerName as String] as? String, owner.hasPrefix("Julius"),
       let name = w[kCGWindowName as String] as? String, name == "Julius" {
        print(w[kCGWindowNumber as String]!)
        break
    }
}
')
if [ -n "$WIN_ID" ]; then
    screencapture -x -l "$WIN_ID" "$OUTPUT"
fi
