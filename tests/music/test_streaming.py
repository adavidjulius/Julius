"""Unit tests for AudioStreamer Range Parsing."""
from src.music.streaming import AudioStreamer


def test_range_header_parsing():
    streamer = AudioStreamer()
    total_size = 1000

    # Start and end
    assert streamer.parse_range("bytes=0-499", total_size) == (0, 499)
    assert streamer.parse_range("bytes=500-999", total_size) == (500, 999)

    # Open end
    assert streamer.parse_range("bytes=500-", total_size) == (500, 999)

    # Suffix range
    assert streamer.parse_range("bytes=-200", total_size) == (800, 999)

    # Invalid range syntax or out of bounds
    assert streamer.parse_range(None, total_size) is None
    assert streamer.parse_range("invalid", total_size) is None
    assert streamer.parse_range("bytes=1500-2000", total_size) is None
    assert streamer.parse_range("bytes=600-400", total_size) is None
