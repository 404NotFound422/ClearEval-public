"""Reproducible stdlib extraction of visible text from saved primary HTML.

This script never fetches, judges scientific claims, fabricates source passages,
or extracts PDF text. Offsets bind the saved normalized text, not HTML bytes.
"""
from pathlib import Path
from html.parser import HTMLParser
import hashlib
import json
import re

VERSION="primary-html-visible-text-v1"
VOID={"area","base","br","col","embed","hr","img","input","link","meta","param","source","track","wbr"}
BLOCK={"p","div","section","article","main","h1","h2","h3","h4","h5","h6","li","tr","br","hr"}
SKIP={"script","style","noscript","svg","iframe","nav","button"}
SELECTORS={
    "MACS_ADVSCI_2020":("article",None),
    "FDISCO_SCIADV_2019":("article",None),
    "FRUIT_FRONTNEUROANAT_2015":("main","ArticleDetailsV4__main"),
}
SEARCH_TERMS={
    "MACS_ADVSCI_2020":["DiI is a commonly used", "preserve the fluorescence of DiI", "MACS clearing protocol"],
    "FDISCO_SCIADV_2019":["incompatibility with some specific tracers", "pH-adjusted", "low temperature"],
    "FRUIT_FRONTNEUROANAT_2015":["one-step treatment with 100% FRUIT", "35% FRUIT", "DiI-labeled mouse brains", "OPTICAL CLEARING USING FRUIT"],
}


def digest_bytes(data):return hashlib.sha256(data).hexdigest()


def digest_text(text):return digest_bytes(text.encode("utf-8"))


class VisiblePrimary(HTMLParser):
    def __init__(self,selector):
        super().__init__(convert_charrefs=True)
        self.selector=selector;self.stack=[];self.parts=[];self.selected=0
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        parent_capture=self.stack[-1][1] if self.stack else False
        parent_skip=self.stack[-1][2] if self.stack else False
        is_root=tag==self.selector[0] and (self.selector[1] is None or self.selector[1] in attrs.get("class","").split())
        if is_root:self.selected+=1
        capture=parent_capture or is_root
        skip=parent_skip or tag in SKIP
        if capture and not skip and tag in BLOCK:self.parts.append(chr(10))
        if tag not in VOID:self.stack.append((tag,capture,skip))
    def handle_endtag(self,tag):
        if self.stack and self.stack[-1][1] and not self.stack[-1][2] and tag in BLOCK:self.parts.append(chr(10))
        for index in range(len(self.stack)-1,-1,-1):
            if self.stack[index][0]==tag:
                del self.stack[index:]
                break
    def handle_data(self,data):
        if self.stack and self.stack[-1][1] and not self.stack[-1][2]:self.parts.append(data)
    def result(self):
        visible=re.sub(r"[^\S\n]+"," ","".join(self.parts))
        return chr(10).join(line.strip() for line in visible.splitlines() if line.strip())+chr(10)


def passages(text,terms):
    lines=[];start=0
    for line in text.splitlines(keepends=True):
        quote=line.rstrip(chr(10))
        lines.append((start,start+len(quote),quote));start+=len(line)
    found=[];seen=set()
    for term in terms:
        candidates=[line for line in lines if term.casefold() in line[2].casefold() and len(line[2])>=60]
        if not candidates:continue
        start,end,quote=candidates[0]
        if (start,end) in seen:continue
        seen.add((start,end))
        found.append({"id":"P"+str(len(found)+1),"start":start,"end":end,"quote":quote,
                      "sha256":digest_text(quote),"locator_search_term":term,
                      "selection":"Literal primary paragraph selected by reproducible keyword; not an entailment label"})
    return found


def main():
    repo=Path(__file__).resolve().parents[2]
    registry_path=repo/"KnowledgeBase/source_registry.json"
    registry=json.loads(registry_path.read_text(encoding="utf-8"))
    indexed={source["id"]:source for source in registry["sources"]}
    summary=[]
    for source_id,source in indexed.items():
        folder=Path(__file__).parent/source_id
        if not folder.exists():continue
        raw=folder/"raw.html"
        if raw.exists() and source_id in SELECTORS:
            html=raw.read_text(encoding="utf-8")
            fetch=json.loads((folder/"fetch.json").read_text(encoding="utf-8-sig"))
            parser=VisiblePrimary(SELECTORS[source_id]);parser.feed(html);text=parser.result()
            failures=[]
            if len(text)<5000 or parser.selected<1:failures.append("PRIMARY_BODY_MISSING_OR_TOO_SHORT")
            if source["identity"]["doi"].casefold() not in html.casefold():failures.append("SOURCE_DOI_NOT_FOUND")
            if any(marker.casefold() in text.casefold() for marker in ("Checking your browser","Just a moment","Access Denied","verify you are human")):
                failures.append("ANTI_BOT_BODY")
            if source["method"].casefold() not in text.casefold():failures.append("METHOD_IDENTITY_NOT_FOUND_IN_BODY")
            if failures:
                status={"status":"FAILED_BODY_VALIDATION","failures":failures,"raw_sha256":digest_bytes(raw.read_bytes())}
                (folder/"validation.json").write_text(json.dumps(status,indent=2)+chr(10),encoding="utf-8")
                source["snapshot"]=None;source["grounding_status"]="UNRESOLVED";source["retrieval_status"]=status
                summary.append({"id":source_id,**status});continue
            text_path=folder/"body.txt";text_path.write_text(text,encoding="utf-8",newline="\n")
            selected=passages(text,SEARCH_TERMS[source_id])
            license_urls=sorted(set(re.findall(r'https?://(?:www\.)?creativecommons\.org/licenses/[^"<>\s]+',html)))
            license_lines=[line for line in text.splitlines() if "creative commons" in line.casefold() and len(line)<2000]
            snapshot={"status":"BOUND_RETRIEVED_PRIMARY_BODY","raw_path":raw.relative_to(repo).as_posix(),
                      "raw_sha256":digest_bytes(raw.read_bytes()),"raw_encoding":fetch.get("transport_saved_encoding"),
                      "text_path":text_path.relative_to(repo).as_posix(),"text_sha256":digest_text(text),
                      "characters":len(text),"identity_url":source["identity"]["url"],"version":source["identity"]["version"],
                      "retrieved_url":fetch.get("final_url"),"requested_url":fetch.get("requested_url"),
                      "fetched_at_utc":fetch.get("fetched_at_utc"),"extraction":{"version":VERSION,
                      "script_sha256":digest_bytes(Path(__file__).read_bytes()),"selector":SELECTORS[source_id],
                      "normalization":"HTML entities decoded; script/style/navigation excluded; whitespace normalized; no prose rewritten"},
                      "license":{"links_found":license_urls,"statements_from_body":license_lines,
                                 "status":"PRIMARY_PAGE_LICENSE_LINKS_RECORDED_PENDING_USER_LICENSE_REVIEW"}}
            source["snapshot"]=snapshot;source["passages"]=selected
            source["grounding_status"]="PRIMARY_BODY_AND_LOCATORS_BOUND_APPLICABILITY_ENTAILMENT_PENDING"
            source["guards"]=["SOURCE_APPLICABILITY_NOT_REVIEWED","SEPARATE_ENTAILMENT_UNBOUND"]
            source["retrieval_status"]={"status":"BODY_VALIDATED","publication_identity":"DOI_AND_METHOD_PRESENT",
                                        "scientific_claims_validated":False}
            (folder/"passages.json").write_text(json.dumps(selected,ensure_ascii=False,indent=2)+chr(10),encoding="utf-8")
            (folder/"snapshot.json").write_text(json.dumps(snapshot,ensure_ascii=False,indent=2)+chr(10),encoding="utf-8")
            summary.append({"id":source_id,"status":snapshot["status"],"characters":len(text),"passages":len(selected)})
        elif (folder/"raw.pdf").exists():
            # Preserve a separately verified published-parser extraction. HTML
            # refresh cannot silently downgrade an already bound PDF body.
            existing=source.get("snapshot") or {}
            if existing.get("status")=="BOUND_RETRIEVED_PRIMARY_PDF_TEXT":
                text_path=repo/existing["text_path"]
                if (digest_bytes((folder/"raw.pdf").read_bytes())!=existing["raw_sha256"]
                        or digest_bytes(text_path.read_bytes())!=existing["text_sha256"]):
                    raise ValueError("Previously bound PDF/body changed; explicit revision required")
                summary.append({"id":source_id,"status":existing["status"],"characters":existing["characters"],
                                "pages":existing["pages"],"passages":len(source.get("passages",[]))})
                continue
            raw=folder/"raw.pdf";data=raw.read_bytes()
            fetch=json.loads((folder/"pdf_fetch.json").read_text(encoding="utf-8-sig"))
            if not data.startswith(b"%PDF-"):
                source["snapshot"]=None;source["retrieval_status"]={"status":"FAILED_PDF_MAGIC_VALIDATION"}
                summary.append({"id":source_id,"status":"FAILED_PDF_MAGIC_VALIDATION"});continue
            snapshot={"status":"RAW_PRIMARY_PDF_BOUND_TEXT_EXTRACTION_PENDING","raw_path":raw.relative_to(repo).as_posix(),
                      "raw_sha256":digest_bytes(data),"bytes":len(data),"identity_url":source["identity"]["url"],
                      "version":source["identity"]["version"],"retrieved_url":fetch.get("final_url"),
                      "requested_url":fetch.get("requested_url"),"fetched_at_utc":fetch.get("fetched_at_utc"),
                      "text_path":None,"text_sha256":None,"license":{"status":"PENDING_DOCUMENT_INSPECTION"}}
            source["snapshot"]=snapshot;source["passages"]=[]
            source["grounding_status"]="UNRESOLVED_PRIMARY_TEXT_EXTRACTION_PENDING"
            source["guards"]=["PRIMARY_TEXT_EXTRACTION_PENDING","SOURCE_APPLICABILITY_NOT_REVIEWED","SEPARATE_ENTAILMENT_UNBOUND"]
            source["retrieval_status"]={"status":"PDF_BYTES_FETCHED","scientific_claims_validated":False,
                                        "html_fetch_status":"FETCH_FAILED"}
            (folder/"snapshot.json").write_text(json.dumps(snapshot,ensure_ascii=False,indent=2)+chr(10),encoding="utf-8")
            summary.append({"id":source_id,"status":snapshot["status"],"bytes":len(data),"passages":0})
    registry["primary_snapshot_summary"]={"html_bodies_bound":sum(item.get("status")=="BOUND_RETRIEVED_PRIMARY_BODY" for item in summary),
                                          "pdf_bytes_bound_text_pending":sum(item.get("status")=="RAW_PRIMARY_PDF_BOUND_TEXT_EXTRACTION_PENDING" for item in summary),
                                          "pdf_texts_bound":sum(item.get("status")=="BOUND_RETRIEVED_PRIMARY_PDF_TEXT" for item in summary),
                                          "scientific_validation":"PENDING_USER_EXPERT","entailment_results_created":0}
    registry_path.write_text(json.dumps(registry,ensure_ascii=False,indent=2)+chr(10),encoding="utf-8")
    (Path(__file__).parent/"retrieval_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+chr(10),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))

if __name__=="__main__":main()