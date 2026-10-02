"""Standard box structure and technical-property probe regressions."""
import struct

import pytest

from fanglei.final_video_qa import _box_rows, _children, _mp4_metadata


def box(kind, payload=b''):
    return struct.pack('>I4s', len(payload) + 8, kind) + payload


def conventional_mp4():
    # One video timing row: 60 samples, 1000 ticks each, at 30000 ticks/s.
    mvhd = box(b'mvhd', b'\0' * 12 + struct.pack('>II', 1000, 2000))
    tkhd = box(b'tkhd', b'\0' * 12 + struct.pack('>I', 1))
    mdhd = box(b'mdhd', b'\0' * 12 + struct.pack('>II', 30000, 60000))
    hdlr = box(b'hdlr', b'\0' * 8 + b'vide')
    fixed = bytearray(78)
    fixed[24:28] = struct.pack('>HH', 320, 240)
    avc1 = box(b'avc1', bytes(fixed) + box(b'avcC', b'\1\x42\0\x1e' + b'\0' * 8))
    stsd = box(b'stsd', b'\0' * 4 + struct.pack('>I', 1) + avc1)
    stts = box(b'stts', b'\0' * 4 + struct.pack('>III', 1, 60, 1000))
    trak = box(b'trak', tkhd + box(b'mdia', mdhd + hdlr + box(b'minf', box(b'stbl', stsd + stts))))
    return box(b'ftyp', b'isom\0\0\0\0') + box(b'moov', mvhd + trak) + box(b'free') + box(b'mdat', b'opaque')


def test_root_walker_accounts_for_entire_standard_file():
    data = conventional_mp4()
    rows = _box_rows(data, 0, len(data))
    assert [row[0] for row in rows] == [b'ftyp', b'moov', b'free', b'mdat']
    assert rows[-1][3] == len(data)


def test_stts_rows_are_not_child_boxes():
    video = _mp4_metadata(conventional_mp4())['video']
    assert video['frame_count'] == 60
    assert video['fps'] == 30
    assert (video['width'], video['height'], video['codec']) == (320, 240, 'h264')


def test_meta_fullbox_prefix_is_skipped():
    data = box(b'udta', box(b'meta', b'\0' * 4 + box(b'hdlr') + box(b'keys') + box(b'ilst')))
    udta = _box_rows(data, 0, len(data))[0]
    meta = _children(data, udta)[0]
    assert [row[0] for row in _children(data, meta)] == [b'hdlr', b'keys', b'ilst']


@pytest.mark.parametrize('child', [struct.pack('>I4s', 100, b'hdlr'), struct.pack('>I4sQ', 1, b'hdlr', 12), b'abc'])
def test_malformed_meta_children_fail_closed(child):
    data = box(b'meta', b'\0' * 4 + child)
    with pytest.raises(ValueError):
        _children(data, _box_rows(data, 0, len(data))[0])


@pytest.mark.parametrize('kind,prefix,child', [(b'avc1', 78, b'avcC'), (b'mp4a', 28, b'esds')])
def test_sample_entry_fixed_fields_are_not_child_boxes(kind, prefix, child):
    entry = box(kind, b'\0' * prefix + box(child))
    data = box(b'stsd', b'\0' * 4 + struct.pack('>I', 1) + entry)
    entries = _children(data, _box_rows(data, 0, len(data))[0])
    assert [row[0] for row in entries] == [kind]
    assert [row[0] for row in _children(data, entries[0])] == [child]


def test_extended_and_to_scope_end_boxes_are_bounded():
    data = struct.pack('>I4sQ', 1, b'free', 16) + struct.pack('>I4s', 0, b'mdat') + b'opaque'
    assert _box_rows(data, 0, len(data))[-1][3] == len(data)
    with pytest.raises(ValueError):
        _box_rows(data, -1, len(data))


def probe_json():
    return {'format': {'format_name': 'mov,mp4,m4a,3gp,3g2,mj2', 'duration': '2.010'},
            'streams': [
                {'codec_type': 'video', 'codec_name': 'h264', 'width': 320, 'height': 240,
                 'avg_frame_rate': '30/1', 'nb_read_frames': '60', 'duration': '2.000'},
                {'codec_type': 'audio', 'codec_name': 'aac', 'sample_rate': '48000',
                 'channels': 2, 'duration': '2.000'}]}


def test_ffprobe_json_is_validated_and_projected():
    from fanglei.final_video_qa import _ffprobe_json_metadata
    result = _ffprobe_json_metadata(probe_json())
    assert result['container_duration_seconds'] == 2.010
    assert result['video']['frame_count'] == 60
    assert result['video']['fps'] == 30
    assert result['audio']['sample_rate'] == 48000


@pytest.mark.parametrize('change', ['infinite_duration', 'zero_denominator', 'bad_frames', 'invalid_streams'])
def test_invalid_ffprobe_properties_fail_closed(change):
    from fanglei.final_video_qa import _ffprobe_json_metadata
    data = probe_json()
    if change == 'infinite_duration': data['format']['duration'] = 'nan'
    elif change == 'zero_denominator': data['streams'][0]['avg_frame_rate'] = '30/0'
    elif change == 'bad_frames': data['streams'][0]['nb_read_frames'] = '-5'
    else: data['streams'] = 'invalid'
    with pytest.raises(ValueError): _ffprobe_json_metadata(data)


def test_ffprobe_subprocess_failure_never_falls_back(tmp_path, monkeypatch):
    import subprocess
    from fanglei.final_video_qa import _ffprobe_metadata
    def failed(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 1, '', 'invalid media')
    monkeypatch.setattr(subprocess, 'run', failed)
    with pytest.raises(ValueError, match='FFPROBE_FAILED'):
        _ffprobe_metadata(tmp_path / 'media.mp4', tmp_path / 'ffprobe')
