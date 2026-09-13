# -*- coding: utf-8 -*-
"""俄语词书全量交付校验:
  - russian_books.json 词数/级别分布
  - sentences_master.json 每词 3 条
  - 游戏 vocabulary/<word>.mp3 音频命中率
  - sentence_audio/<md5(ru)>.mp3 命中率
  - wcpFullEng.db / wcpOnlyWord.db pron + sentence2 全查
  - MyBook.es3 槽位 3 词数 (槽位 1 日语/槽位 2 法语不动)
  - 导入文件存在性
用法: python tools/verify_all_ru.py
"""
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
import wcp_paths

ROOT = Path(__file__).resolve().parent.parent
VOCAB_DIR = Path.home() / 'AppData' / 'LocalLow' / 'WCP' / 'vocabulary'
SENT_DIR = Path.home() / 'AppData' / 'LocalLow' / 'WCP' / 'wcp' / 'sentence_audio'
MYBOOK = Path.home() / 'AppData' / 'LocalLow' / 'WCP' / 'wcp' / 'MyBook.es3'

ok_all = True


def report(label, ok, detail=''):
    global ok_all
    if not ok:
        ok_all = False
    print(f"[{'OK' if ok else 'NG'}] {label}" + (f' {detail}' if detail else ''))


def main():
    books = json.loads((ROOT / 'output' / 'russian_books.json').read_text(
        encoding='utf-8'))
    levels = books['levels']
    n_words = {lv: len(levels[lv]) for lv in levels}
    all_words = [w for lv in levels for w in levels[lv]]
    report('词书构建', True,
           f"{n_words} 合计 {len(all_words)}")

    master = json.loads((ROOT / 'data' / 'translations' / 'sentences_master.json')
                        .read_text(encoding='utf-8'))
    short = [w['word'] for w in all_words if len(master.get(w['word'], [])) < 3]
    report('例句 master (每词3条)', not short,
           f'{len(master)} 词' + (f', 缺: {short[:5]}' if short else ''))

    # 音频
    miss_w = [w['word'] for w in all_words
              if not (VOCAB_DIR / f"{w['word']}.mp3").exists()]
    report('单词音频 vocabulary/', len(miss_w) == 0,
           f'{len(all_words) - len(miss_w)}/{len(all_words)}'
           + (f', 缺: {miss_w[:5]}' if miss_w else ''))

    sent_uni = {ru for v in master.values() for ru, _ in v}
    miss_s = [ru for ru in sent_uni
              if not (SENT_DIR / (hashlib.md5(ru.encode('utf-8')).hexdigest()
                                 + '.mp3')).exists()]
    report('例句音频 sentence_audio/', len(miss_s) == 0,
           f'{len(sent_uni) - len(miss_s)}/{len(sent_uni)}'
           + (f', 缺例: {miss_s[:2]}' if miss_s else ''))

    # 游戏库
    words_set = {w['word'] for w in all_words}
    for db_path, with_sent in ((wcp_paths.full_db(), True),
                               (wcp_paths.only_db(), False)):
        con = sqlite3.connect(str(db_path))
        cur = con.cursor()
        wl = list(words_set)
        miss_p = 0
        for i in range(0, len(wl), 500):
            chunk = wl[i:i + 500]
            p = ','.join('?' * len(chunk))
            n = cur.execute(f'SELECT COUNT(*) FROM pron WHERE word IN ({p})',
                            chunk).fetchone()[0]
            miss_p += len(chunk) - n
        report(f'{db_path.name} pron', miss_p == 0,
               f'{len(wl) - miss_p}/{len(wl)}')
        if with_sent:
            miss_s2 = 0
            bad_s2 = 0
            for i in range(0, len(wl), 500):
                chunk = wl[i:i + 500]
                p = ','.join('?' * len(chunk))
                cnt = dict(cur.execute(
                    f'SELECT word, COUNT(*) FROM sentence2 WHERE word IN ({p}) '
                    f'GROUP BY word', chunk).fetchall())
                miss_s2 += sum(1 for w in chunk if cnt.get(w, 0) < 3)
            sample = cur.execute(
                'SELECT sentences FROM sentence2 WHERE word=?',
                (wl[0],)).fetchall()
            bad_s2 = sum(1 for (s,) in sample
                         if not (s.startswith('例句：') and s.endswith('）')))
            report(f'{db_path.name} sentence2(每词>=3)', miss_s2 == 0,
                   f'缺例词 {miss_s2}, 格式异常抽检 {bad_s2}/{len(sample)}')
            print('   样例:', sample[0][0][:60] if sample else '-')
        con.close()

    # MyBook (合并单册: 槽位3 = 全部词, 槽位4 空, 槽位1/2 日法书不动)
    doc = json.loads(MYBOOK.read_text(encoding='utf-8-sig'))
    want = {w['word'] for w in all_words}
    got = set(doc.get('SelfBookList3', {}).get('value', []))
    dct = doc.get('wordDictionary3', {}).get('value', {})
    report('MyBook 槽位3(俄语合并单册)',
           got == want and all(w in dct for w in got),
           f'{len(got)}/{len(want)} 词')
    n4 = len(doc.get('SelfBookList4', {}).get('value', []))
    report('MyBook 槽位4 空', n4 == 0, f'{n4} 词')
    jp = doc.get('SelfBookList1', {}).get('value', [])
    report('MyBook 槽位1 日语书保留', len(jp) == 7922, f'{len(jp)} 词')
    fr = doc.get('SelfBookList2', {}).get('value', [])
    report('MyBook 槽位2 法语书保留', len(fr) == 8116, f'{len(fr)} 词')

    # 导入文件
    imp = ROOT / 'output' / 'import'
    for f in ('俄语A1A2.xlsx', '俄语B1.xlsx', '俄语B2.xlsx', 'wcp_russian.db'):
        report(f'导入文件 {f}', (imp / f).exists())
    pdir = Path.home() / 'AppData' / 'LocalLow' / 'WCP' / 'wcp'
    for f in ('俄语A1A2.xlsx', '俄语B1.xlsx', '俄语B2.xlsx', 'wcp_russian.db'):
        report(f'persistentDataPath {f}', (pdir / f).exists())

    print('\n总体:', 'ALL PASS' if ok_all else '存在未通过项')


if __name__ == '__main__':
    main()
