# -*- coding: utf-8 -*-
"""皮肤资源单向同步：主程序 images/*/sk/*.webp -> 本仓 -> GitHub -> jsDelivr。

设计要点：
  * 按原 URL 路径平铺，不打包、不改文件名（webp 再压缩无收益，实测反而变大）。
  * 变更检测用「路径 + size + mtime_ns」轻量指纹，不逐文件算 sha256（12901 张太慢）。
  * 无变更不产生空提交 / 空 tag；与 sgs-data 的版本、tag 完全解耦。
  * manifest.json 只记版本级摘要 + 整体指纹，不列 12901 条（App 不按它下载）。
"""
import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = Path(os.environ.get(
    'SGS_MAIN', str(ROOT.parent.parent / 'sgs-heroes-app')))
SRC = MAIN / 'images'
OUT = ROOT / 'images'
GH = 'liu2547259736/sgs-skins'
BRANCH = 'main'
STATE = ROOT / 'tools' / 'sync-state.json'
MANIFEST = ROOT / 'manifest.json'
# cdn.jsdelivr.net 在国内直连 TLS 握手失败（2026-11-12/16 实测），
# gcore / testingcf 可直连；manifest 的 cdn_base 与 App 默认源必须一致。
CDN = 'https://gcore.jsdelivr.net/gh/%s@%s/' % (GH, BRANCH)


def run(cmd, timeout=1800):
    return subprocess.run(cmd, cwd=str(ROOT), capture_output=True,
                          text=True, encoding='utf-8', errors='replace',
                          timeout=timeout)


def git(*args, timeout=1800):
    return run(['git', *args], timeout=timeout)


def log(msg):
    print(msg, flush=True)


def scan_source():
    """{ 'images/<ver>/sk/<name>.webp': (size, mtime_ns) }"""
    if not SRC.is_dir():
        raise RuntimeError('找不到主程序 images 目录: %s' % SRC)
    out = {}
    for ver_dir in sorted(p for p in SRC.iterdir() if p.is_dir()):
        sk = ver_dir / 'sk'
        if not sk.is_dir():
            continue
        for f in sk.rglob('*.webp'):
            if not f.is_file():
                continue
            rel = f.relative_to(MAIN).as_posix()
            st = f.stat()
            out[rel] = (st.st_size, st.st_mtime_ns)
    return out


def fingerprint(entries):
    h = hashlib.sha256()
    for rel in sorted(entries):
        size, mt = entries[rel]
        h.update(('%s|%d|%d\n' % (rel, size, mt)).encode('utf-8', 'replace'))
    return h.hexdigest()


def load_state():
    try:
        return json.loads(STATE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, STATE)


def atomic_json(path, data):
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, path)


def mirror(entries):
    """增量镜像；源里已删除的文件从仓里移除。返回 (新增, 更新, 删除)。"""
    OUT.mkdir(parents=True, exist_ok=True)
    want = set(entries)
    added = changed = removed = 0
    for f in list(OUT.rglob('*.webp')):
        rel = f.relative_to(ROOT).as_posix()
        if rel not in want:
            f.unlink()
            removed += 1
    for rel, (size, mt) in entries.items():
        src = MAIN / rel
        dst = ROOT / rel
        exists = dst.exists()
        if exists:
            st = dst.stat()
            if st.st_size == size and st.st_mtime_ns == mt:
                continue
            changed += 1
        else:
            added += 1
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return added, changed, removed


def build_manifest(entries, version, fp):
    by_ver = {}
    total = 0
    for rel, (size, _) in entries.items():
        parts = rel.split('/')
        ver = parts[1] if len(parts) > 1 else '?'
        d = by_ver.setdefault(ver, {'files': 0, 'bytes': 0})
        d['files'] += 1
        d['bytes'] += size
        total += size
    return {
        'schema': 1,
        'version': version,
        'updated_at': datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
        'cdn_base': CDN,
        'counts': {'files': len(entries), 'bytes': total},
        'versions': dict(sorted(by_ver.items())),
        'fingerprint': fp,
    }


def next_version():
    base = datetime.date.today().strftime('%Y.%m.%d')
    r = git('tag', '--list', 'skins-v%s*' % base)
    tags = [t.strip() for t in (r.stdout or '').splitlines() if t.strip()]
    if not tags:
        return base
    n = 1
    prefix = 'skins-v' + base
    for t in tags:
        suffix = t[len(prefix):]
        if suffix.startswith('-'):
            try:
                n = max(n, int(suffix[1:]) + 1)
            except ValueError:
                pass
    return '%s-%d' % (base, n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='只输出 CHANGED / UNCHANGED')
    ap.add_argument('--commit', action='store_true')
    ap.add_argument('--push', action='store_true')
    ap.add_argument('--tag', action='store_true')
    ap.add_argument('--force', action='store_true', help='无视指纹强制发布')
    ap.add_argument('--note', default='')
    a = ap.parse_args()

    entries = scan_source()
    fp = fingerprint(entries)
    state = load_state()
    changed = (state.get('fingerprint') != fp) or a.force
    log('扫描主程序: %d 张皮肤 / %.1f MB / 指纹 %s'
        % (len(entries), sum(v[0] for v in entries.values()) / 1048576, fp[:12]))
    if a.check:
        log('CHANGED' if changed else 'UNCHANGED')
        return 0
    if not changed:
        log('无变更，跳过（不产生空提交 / 空 tag）')
        return 0

    added, upd, removed = mirror(entries)
    log('镜像完成: 新增 %d / 更新 %d / 删除 %d' % (added, upd, removed))

    version = next_version()
    atomic_json(MANIFEST, build_manifest(entries, version, fp))
    log('manifest: version=%s cdn=%s' % (version, CDN))

    if a.commit:
        r = git('add', '-A')
        if r.returncode:
            raise RuntimeError('git add 失败: %s' % r.stderr[-400:])
        msg = 'sync skins %s: +%d ~%d -%d' % (version, added, upd, removed)
        if a.note:
            msg += ' | ' + a.note[:120]
        r = git('-c', 'user.name=sgs-sync', '-c', 'user.email=sync@local',
                'commit', '-m', msg)
        if r.returncode:
            log('commit 提示: %s' % (r.stdout or r.stderr).strip()[-300:])
        else:
            log('committed: %s' % msg)

    if a.push:
        r = git('push', 'origin', BRANCH, timeout=3600)
        if r.returncode:
            raise RuntimeError('git push 失败: %s' % (r.stderr or '')[-600:])
        log('pushed origin/%s' % BRANCH)
        if a.tag:
            tag = 'skins-v' + version
            git('tag', '-f', tag)
            r = git('push', 'origin', tag, timeout=600)
            if r.returncode:
                log('tag push 警告: %s' % (r.stderr or '')[-300:])
            else:
                log('tag pushed: %s' % tag)

    state.update({'fingerprint': fp, 'version': version,
                  'files': len(entries), 'synced_at':
                  datetime.datetime.now().astimezone().isoformat(timespec='seconds')})
    save_state(state)
    log('同步完成 OK')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print('ERROR: %s' % exc, file=sys.stderr, flush=True)
        sys.exit(1)
