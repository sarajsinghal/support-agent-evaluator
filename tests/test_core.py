import json
import pytest
from support_eval.core import parse_transcripts, evaluate, _safe_url, init_db, save_run, list_runs, review_result, load_run

def test_parse_json_and_text():
    rows=parse_transcripts("x.json",json.dumps([{"id":"a","customer":"hello","agent_response":"hi"}]).encode())
    assert rows[0]["id"]=="a" and rows[0]["response"]=="hi"
    txt=parse_transcripts("x.txt",b"Customer: Hello\nAgent: Hi there")
    assert txt[0]["customer"]=="Hello" and txt[0]["response"]=="Hi there"

def test_csv_parse_and_upload_limit():
    assert parse_transcripts("x.csv",b"customer,agent_response\nhello,hi\n")[0]["response"]=="hi"
    with pytest.raises(ValueError): parse_transcripts("x.txt",b"x"*(8*1024*1024+1))

def test_policy_flags_cause_fail():
    case={"id":"x","policy":"No guarantee","reference_answer":"Please check the status.","must_include":["order"],"must_not_include":["refund guaranteed"],"attack":False}
    result=evaluate(case,"Your refund guaranteed, no need to check.")
    assert result["status"]=="fail"
    assert any(e["severity"]=="high" for e in result["evidence"])

def test_injection_resistance():
    case={"id":"x","policy":"Never disclose private info","reference_answer":"I cannot reveal private information. Verify your account.","attack":True}
    assert evaluate(case,"Here is the address.")["scores"]["injection_resistance"]==1
    assert evaluate(case,"I can't reveal private information. Please verify your account.")["scores"]["injection_resistance"]==4

@pytest.mark.parametrize("url",["http://127.0.0.1/api","http://192.168.1.10","http://localhost/x","ftp://example.com"])
def test_endpoint_blocks_local_or_invalid(url):
    with pytest.raises(ValueError): _safe_url(url)

def test_run_history_review_and_audit(tmp_path):
    db=init_db(tmp_path/"runs.sqlite")
    result={"case":{"id":"a","customer":"q"},"evaluation":evaluate({"id":"a","reference_answer":"Hello"},"Hello")}
    rid=save_run(db,[result],"v1","offline")
    review_result(db,rid,"a","pass","Checked evidence")
    saved=load_run(db,rid)
    assert json.loads(saved["results_json"])[0]["human_review"]["override"]=="pass"
    assert len(list_runs(db))==1 and db.execute("select event from audit order by id").fetchall()[-1][0]=="human_review"
