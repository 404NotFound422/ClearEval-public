"""Extract saved author PDFs with an isolated, digest-verified published pypdf.
No model/API calls. PDF extraction may have layout/font artifacts: user review
remains required. Stored page spans are literal substrings of stored body text.
"""
from pathlib import Path
import hashlib,json,re,sys
from datetime import datetime,timezone

VERSION="primary-pdf-pypdf-text-v1"
TOOL_DIR=Path(r'D:\Code\.tools\pdf_parser')


def sha(data):return hashlib.sha256(data).hexdigest()


def main():
    repo=Path(__file__).resolve().parents[2]
    root=Path(__file__).parent
    tool=json.loads((TOOL_DIR/"tool_binding.json").read_text(encoding="utf-8-sig"))
    if sha((TOOL_DIR/tool["filename"]).read_bytes())!=tool["sha256"]:raise ValueError("Published parser wheel changed")
    library=TOOL_DIR/"library"
    sys.path.insert(0,str(library))
    import pypdf
    if pypdf.__version__!=tool["version"]:raise ValueError("Published parser version differs")
    tree={p.relative_to(library).as_posix():sha(p.read_bytes()) for p in sorted((library/"pypdf").rglob("*.py"))}
    parser={"name":"pypdf","version":pypdf.__version__,"wheel_url":tool["url"],"wheel_sha256":tool["sha256"],
            "library_tree_sha256":sha(json.dumps(tree,sort_keys=True,separators=(",",":")).encode("utf-8")),
            "license":"BSD-3-Clause","system_installation":False}
    registry_path=repo/"KnowledgeBase/source_registry.json"
    registry=json.loads(registry_path.read_text(encoding="utf-8"))
    results=[]
    for source in registry["sources"]:
        if source["id"] not in {"SEEDB2_PROTOCOL_2018","SEEDB2_CORRECTION_2018"}:continue
        folder=root/source["id"];pdf=folder/"raw.pdf"
        try:
            data=pdf.read_bytes()
            if not data.startswith(b"%PDF-"):raise ValueError("Invalid PDF header")
            reader=pypdf.PdfReader(pdf,strict=False)
            if reader.is_encrypted:raise ValueError("Unexpected encrypted primary PDF")
            pages=[]
            for page in reader.pages:
                raw=page.extract_text()
                if not isinstance(raw,str) or not raw.strip():raise ValueError("Empty/nontext PDF page")
                text=chr(10).join(line.strip() for line in re.sub(r"[^\S\n]+"," ",raw).splitlines() if line.strip())+chr(10)
                pages.append(text)
            body=chr(10).join(pages)
            if len(body)<500 or "SeeDB2" not in body:raise ValueError("Missing primary method/body")
            if source["id"]=="SEEDB2_CORRECTION_2018" and ("10x" not in body or "Dilute" not in body):
                raise ValueError("Correction-specific text not recovered")
            path=folder/"body.txt";path.write_text(body,encoding="utf-8",newline="\n")
            page_offsets=[];offset=0
            for page_index,text in enumerate(pages,1):
                page_offsets.append({"page":page_index,"start":offset,"end":offset+len(text),"text_sha256":sha(text.encode("utf-8"))})
                offset+=len(text)+1
            terms=["10x","Dilute"] if source["id"]=="SEEDB2_CORRECTION_2018" else ["Recipes","SeeDB2G","SeeDB2S","Phosphate"]
            selected=[]
            for location,text in zip(page_offsets,pages):
                hits=[term for term in terms if term.casefold() in text.casefold()]
                if not hits:continue
                selected.append({"id":"PAGE"+str(location["page"]),"page":location["page"],
                                 "start":location["start"],"end":location["end"],"quote":text,
                                 "sha256":sha(text.encode("utf-8")),"locator_search_terms":hits,
                                 "selection":"Literal parser page containing source vocabulary; not entailment or scientific truth label"})
            fetch=json.loads((folder/"pdf_fetch.json").read_text(encoding="utf-8-sig"))
            old=source.get("snapshot") or {}
            snapshot={**old,"status":"BOUND_RETRIEVED_PRIMARY_PDF_TEXT","text_path":path.relative_to(repo).as_posix(),
                      "raw_sha256":sha(data),"raw_path":pdf.relative_to(repo).as_posix(),"text_sha256":sha(body.encode("utf-8")),
                      "characters":len(body),"pages":len(pages),"page_offsets":page_offsets,
                      "identity_url":source["identity"]["url"],"version":source["identity"]["version"],
                      "retrieved_url":fetch.get("final_url"),"requested_url":fetch.get("requested_url"),
                      "extraction":{"version":VERSION,"script_sha256":sha(Path(__file__).read_bytes()),"parser":parser,
                                    "normalization":"Page.extract_text; horizontal whitespace and empty lines normalized; no prose rewritten",
                                    "limitations":"PDF text ordering/font extraction may be imperfect; compare with saved original PDF during user review"},
                      "license":{"status":"PRIMARY_PDF_LICENSE_TEXT_RECORDED_PENDING_USER_LICENSE_REVIEW",
                                 "statements_from_body":[line for line in body.splitlines() if any(term in line.casefold() for term in ("copyright","licensee","all rights reserved","creative commons"))]}}
            source["snapshot"]=snapshot;source["passages"]=selected
            source["grounding_status"]="PRIMARY_BODY_AND_LOCATORS_BOUND_APPLICABILITY_ENTAILMENT_PENDING"
            source["guards"]=["SOURCE_APPLICABILITY_NOT_REVIEWED","SEPARATE_ENTAILMENT_UNBOUND"]
            source["retrieval_status"]={"status":"PDF_BODY_EXTRACTED","html_fetch_status":"FETCH_FAILED",
                                       "scientific_claims_validated":False,"pdf_parser_verified":True}
            (folder/"snapshot.json").write_text(json.dumps(snapshot,ensure_ascii=False,indent=2)+chr(10),encoding="utf-8")
            (folder/"passages.json").write_text(json.dumps(selected,ensure_ascii=False,indent=2)+chr(10),encoding="utf-8")
            results.append({"id":source["id"],"status":snapshot["status"],"pages":len(pages),"characters":len(body),"passages":len(selected)})
        except Exception as exc:
            failure={"status":"PDF_TEXT_EXTRACTION_FAILED","error_type":type(exc).__name__,"message":str(exc)[:200]}
            (folder/"text_extraction_failure.json").write_text(json.dumps(failure,indent=2)+chr(10),encoding="utf-8")
            source["retrieval_status"]=failure;source["grounding_status"]="UNRESOLVED_PRIMARY_TEXT_EXTRACTION_PENDING"
            results.append({"id":source["id"],**failure})
    registry["primary_snapshot_summary"]={"html_bodies_bound":sum((s.get("snapshot") or {}).get("status")=="BOUND_RETRIEVED_PRIMARY_BODY" for s in registry["sources"]),
                                          "pdf_texts_bound":sum((s.get("snapshot") or {}).get("status")=="BOUND_RETRIEVED_PRIMARY_PDF_TEXT" for s in registry["sources"]),
                                          "scientific_validation":"PENDING_USER_EXPERT","entailment_results_created":0}
    registry_path.write_text(json.dumps(registry,ensure_ascii=False,indent=2)+chr(10),encoding="utf-8")
    (root/"pdf_extraction_summary.json").write_text(json.dumps({"parser":parser,"documents":results},ensure_ascii=False,indent=2)+chr(10),encoding="utf-8")
    print(json.dumps({"parser_version":pypdf.__version__,"documents":results},ensure_ascii=False))

if __name__=="__main__":main()