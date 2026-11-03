"""Words with several stress variants in the dictionary and their use in the corpus (for resolving homonyms)."""
import sys,csv,re,json,collections,hashlib,os
from tools import paths
from ukrainian_word_stress.stressify_ import _load_dictionary,_trie_value,_parse_dictionary_value
from tools.voice import pipeline as hp, synth as g
d=_load_dictionary()
W=re.compile(r"[А-Яа-яІіЇїЄєҐґ'’]+")
def variants(w):
    v=_trie_value(d,w)
    if v is None: return []
    out=[]
    for tags,acc in _parse_dictionary_value(v[0]):
        if len(acc)==1:
            f=w.lower()[:acc[0]]+'´'+w.lower()[acc[0]:]
            if f not in out: out.append(f)
    return out
def collect():
    from tools.text import public
    public.ensure_table()
    rows=[r for r in csv.DictReader(open(paths.TRANSLATIONS,encoding='utf-8-sig',newline='')) if r['status'] in('machine','edited','user','recorded') and r['name'].startswith('dlg_')]
    occ=collections.defaultdict(list); seen=set()
    for r in rows:
        for s in hp.sentences(g.fix_text(r['uk'])):
            p=hp.prepare(s)
            for i,m in enumerate(W.finditer(p)):
                w=m.group(0); lw=w.lower()
                if sum(c in 'аеєиіїоуюя' for c in lw)<2: continue
                vs=variants(w)
                if len(vs)>1:
                    key=(lw,hashlib.sha1((p+'|'+str(i)).encode()).hexdigest()[:12])
                    if key in seen: continue
                    seen.add(key); occ[lw].append((p,i,r['source']))
    return occ
if __name__=='__main__':
    occ=collect()
    json.dump({w:[(p,i,src) for p,i,src in v] for w,v in occ.items()},open(os.path.join(paths.WORK,'homograph_occ.json'),'w',encoding='utf-8'),ensure_ascii=False)
    items=sorted(occ.items(),key=lambda kv:-len(kv[1]))
    print(len(items),'слів;',sum(len(v) for _,v in items),'вживань')
    open(os.path.join(paths.WORK,'homograph_words.txt'),'w',encoding='utf-8').write('\n'.join(f"{w}|{len(v)}|{' / '.join(x.replace('´','^') for x in variants(w))}" for w,v in items))
