from __future__ import annotations
import io, json, os
from pathlib import Path
import pandas as pd
import streamlit as st
try:
    import plotly.express as px
except ImportError:
    px = None
from dotenv import load_dotenv
from support_eval.core import DIMENSIONS, evaluate, parse_transcripts, call_agent, openai_compatible_judge, init_db, save_run, list_runs, load_run, review_result
from support_eval.scenarios import SCENARIOS

def excel_bytes(df):
    b=io.BytesIO()
    try:
        with pd.ExcelWriter(b,engine="openpyxl") as writer: df.to_excel(writer,index=False,sheet_name="Evaluation")
    except ImportError:
        return None
    return b.getvalue()

def pdf_bytes(run,results):
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except ImportError:
        return None
    b=io.BytesIO(); c=canvas.Canvas(b,pagesize=letter); w,h=letter; y=h-48
    c.setTitle("Support Agent Evaluation")
    c.setFont("Helvetica-Bold",16); c.drawString(44,y,"Support Agent Evaluation Report"); y-=25
    c.setFont("Helvetica",10)
    for line in [f"Run {run['id']} · Version {run['agent_version']}",f"Mode: {run['mode']} · Cases: {len(results)}",f"Average score: {run['average']} / 5 · Outcome: {run['status']}","Automated assessments are probabilistic decision support, not compliance certification."]:
        c.drawString(44,y,line); y-=16
    y-=8
    for item in results:
        case=item["case"]; ev=item["evaluation"]
        if y<100: c.showPage(); y=h-48; c.setFont("Helvetica",10)
        c.setFont("Helvetica-Bold",11); c.drawString(44,y,f"{case['id']} · {case.get('category','')} · {ev['average']}/5 · {ev['status']}"); y-=15
        c.setFont("Helvetica",9)
        for key,text in [("Customer",case.get("customer","")),("Response",ev.get("response","")),("Evidence", "; ".join(x.get("text","") for x in ev.get("evidence",[])) or "No deterministic flags")]:
            wrapped=(key+": "+str(text))
            for start in range(0,len(wrapped),105):
                if y<45: c.showPage(); y=h-48; c.setFont("Helvetica",9)
                c.drawString(48,y,wrapped[start:start+105]); y-=12
        y-=8
    c.save(); return b.getvalue()

ROOT=Path(__file__).parent
load_dotenv(ROOT/".env")
(ROOT/"data").mkdir(exist_ok=True)
DB=init_db(ROOT/"data"/"evaluation.sqlite")
st.set_page_config(page_title="Support Agent Evaluator",page_icon="◈",layout="wide",initial_sidebar_state="expanded")
st.markdown("""<style>
.block-container{padding-top:2rem;padding-bottom:3rem;max-width:1440px}.hero{padding:1.5rem 1.7rem;border-radius:18px;background:linear-gradient(120deg,#153f38,#267c67);color:#fff;margin-bottom:1.3rem}.hero p{opacity:.83;margin:0}.hero h1{color:white;margin:.1rem 0 .5rem;font-size:2.2rem}.eyebrow{text-transform:uppercase;letter-spacing:.15em;font-size:.72rem;font-weight:700;opacity:.8}.small-note{color:#65746d;font-size:.9rem}.stTabs [data-baseweb="tab-list"]{gap:1.5rem}
</style>""",unsafe_allow_html=True)
st.markdown('<div class="hero"><div class="eyebrow">QUALITY · SAFETY · REGRESSION</div><h1>Support Agent Evaluator</h1><p>Evidence-led evaluation for customer support agents, across uploaded transcripts and live test scenarios.</p></div>',unsafe_allow_html=True)
with st.sidebar:
    st.markdown("### Evaluation setup")
    version=st.text_input("Agent version",value="agent-v1",help="Use a stable label so runs can be compared.")
    mode=st.radio("Mode",["Offline transcripts","Live endpoint"],horizontal=False)
    st.divider()
    st.markdown("**Judge**")
    use_judge=st.toggle("Enable optional LLM judge",value=False)
    provider=st.selectbox("Provider format",["OpenAI-compatible chat completions"])
    judge_url=st.text_input("Provider base URL",value=os.getenv("JUDGE_BASE_URL",""),disabled=not use_judge,placeholder="https://provider.example/v1")
    judge_model=st.text_input("Judge model",value=os.getenv("JUDGE_MODEL",""),disabled=not use_judge)
    judge_key=st.text_input("Judge API key",value=os.getenv("JUDGE_API_KEY",""),type="password",disabled=not use_judge,help="Held in memory for this session only. Never saved in run history.")
    st.caption("Judge scores are probabilistic and require human review for high-impact decisions.")
judge=None
if use_judge:
    if judge_url and judge_model and judge_key:
        try: judge=openai_compatible_judge(judge_url,judge_model,judge_key)
        except Exception as e: st.error(f"Judge configuration: {e}")
    else: st.info("Enter a provider URL, model, and key to enable judging. No provider is assumed.")

tab_dash,tab_run,tab_reviews,tab_library=st.tabs(["Overview","Run evaluation","Review & history","Scenario library"])

with tab_dash:
    st.subheader("Benchmark overview")
    runs=list_runs(DB)
    if not runs:
        st.info("No saved evaluations yet. Run an offline benchmark or connect an agent to start building your history.")
    else:
        latest=runs[0]; c1,c2,c3,c4=st.columns(4)
        c1.metric("Saved runs",len(runs)); c2.metric("Latest score",f"{latest['average']:.2f} / 5"); c3.metric("Latest outcome",latest["status"].title()); c4.metric("Cases",latest["case_count"])
        frame=pd.DataFrame(runs)
        if len(frame)>1:
            if px: st.plotly_chart(px.line(frame.sort_values("id"),x="id",y="average",color="agent_version",markers=True,title="Run score by version"),use_container_width=True)
            else: st.line_chart(frame.set_index("id")["average"])
        st.dataframe(frame.rename(columns={"id":"Run","created_at":"Created (UTC)","agent_version":"Version","mode":"Mode","case_count":"Cases","average":"Score / 5","status":"Outcome"}),use_container_width=True,hide_index=True)
        st.caption("Scores summarize this app’s selected cases and rubric; they are not compliance certifications or population performance claims.")

with tab_run:
    st.subheader("Run a benchmark")
    if mode=="Offline transcripts":
        up=st.file_uploader("Upload CSV, JSON, or TXT transcripts",type=["csv","json","txt"],help="Maximum 8 MB. Use customer/user and response/agent_response fields, or messages with role and content.")
        if up:
            try: cases=parse_transcripts(up.name,up.getvalue()); st.success(f"Loaded {len(cases)} conversation(s). Upload is processed in this session and not saved to disk.")
            except Exception as e: cases=[]; st.error(f"Could not read upload: {e}")
        else: cases=[]
        st.caption("Optional judge requests send the selected transcript and reference context to the configured provider only after you start a run.")
    else:
        st.warning("Live testing sends each selected customer scenario to the endpoint you enter. Use a test environment and avoid real customer personal data.")
        endpoint=st.text_input("Agent endpoint URL",placeholder="https://your-agent.example/api/chat")
        auth_type=st.selectbox("Authentication",["None","Bearer token","API key header"])
        token=st.text_input("Bearer token",type="password",disabled=auth_type!="Bearer token")
        header_name=st.text_input("API key header name",value="X-API-Key",disabled=auth_type!="API key header")
        header_value=st.text_input("API key header value",type="password",disabled=auth_type!="API key header")
        timeout=st.slider("Request timeout (seconds)",5,60,20)
        picked=st.multiselect("Scenarios",[x["id"] for x in SCENARIOS],default=[x["id"] for x in SCENARIOS[:4]],format_func=lambda x:next(s["category"]+" · "+s["language"] for s in SCENARIOS if s["id"]==x))
        cases=[{**s,"response":""} for s in SCENARIOS if s["id"] in picked]
    if cases:
        st.dataframe(pd.DataFrame([{"ID":c["id"],"Category":c["category"],"Language":c["language"],"Customer prompt":c["customer"][:100]} for c in cases]),use_container_width=True,hide_index=True)
    if st.button("Run evaluation",type="primary",disabled=not cases):
        results=[]; progress=st.progress(0); status=st.empty(); bar=st.status("Evaluating selected cases…",expanded=True)
        for i,case in enumerate(cases):
            try:
                response=case.get("response","")
                if mode=="Live endpoint":
                    if not endpoint: raise ValueError("Enter the agent endpoint URL.")
                    response=call_agent(endpoint,case["customer"],auth_type=auth_type,token=token,header_name=header_name,header_value=header_value,timeout=timeout)
                ev=evaluate(case,response,judge=judge); results.append({"case":case,"evaluation":ev})
                bar.write(f"{case['id']}: {ev['status']} · {ev['average']}/5")
            except Exception as e:
                results.append({"case":case,"evaluation":{"scores":{},"average":0,"status":"needs review","evidence":[{"dimension":"execution","severity":"high","text":str(e)}],"explanations":{},"response":"","scoring_source":"request failed"}})
                bar.write(f"{case['id']}: request failed")
            progress.progress((i+1)/len(cases))
        rid=save_run(DB,results,version,"offline" if mode=="Offline transcripts" else "live")
        bar.update(label=f"Run {rid} saved",state="complete",expanded=False)
        st.session_state["last_run_id"]=rid
        st.success(f"Evaluation complete · Run {rid}")
        st.rerun()

with tab_reviews:
    st.subheader("Run history & human review")
    runs=list_runs(DB)
    if runs:
        choices={f"Run {r['id']} · {r['agent_version']} · {r['average']}/5 · {r['status']}":r["id"] for r in runs}
        selected=st.selectbox("Select a run",list(choices)); rid=choices[selected]; run=load_run(DB,rid); results=json.loads(run["results_json"])
        flat=[]
        for r in results:
            c=r["case"]; e=r["evaluation"]
            flat.append({"Case":c["id"],"Category":c.get("category"),"Language":c.get("language"),"Score":e["average"],"Outcome":e["status"],"Response":e.get("response","")[:160],"Human override":(r.get("human_review") or {}).get("override","")})
        st.dataframe(pd.DataFrame(flat),use_container_width=True,hide_index=True)
        st.markdown("#### Case details")
        case_idx=st.selectbox("Case",range(len(results)),format_func=lambda i:results[i]["case"]["id"]+" · "+results[i]["case"].get("category",""))
        item=results[case_idx]; ev=item["evaluation"]; case=item["case"]
        st.markdown(f"**Customer:** {case['customer']}\n\n**Agent response:** {ev.get('response') or 'No response captured'}")
        dims=pd.DataFrame([{"Dimension":k.replace("_"," ").title(),"Score / 5":v,"Explanation":ev.get("explanations",{}).get(k,"")} for k,v in ev.get("scores",{}).items()]); st.dataframe(dims,use_container_width=True,hide_index=True)
        if ev.get("evidence"): st.dataframe(pd.DataFrame(ev["evidence"]),use_container_width=True,hide_index=True)
        st.caption(f"Scoring: {ev.get('scoring_source','unknown')}. Automated scores are decision support; use human review for high-impact decisions.")
        with st.form("review"):
            override=st.selectbox("Human review outcome",["No override","pass","fail","needs review"])
            notes=st.text_area("Reviewer notes")
            save=st.form_submit_button("Save review")
            if save:
                review_result(DB,rid,case["id"],"" if override=="No override" else override,notes); st.success("Review and audit entry saved."); st.rerun()
        st.markdown("#### Export this run")
        export_rows=[]
        for r in results:
            c=r["case"]; e=r["evaluation"]; export_rows.append({"run_id":rid,"version":run["agent_version"],"case_id":c["id"],"category":c.get("category"),"language":c.get("language"),"customer":c["customer"],"response":e.get("response",""),"average":e["average"],"status":e["status"],"scores":json.dumps(e.get("scores",{})),"evidence":json.dumps(e.get("evidence",[]),ensure_ascii=False),"human_review":json.dumps(r.get("human_review",{}),ensure_ascii=False)})
        df=pd.DataFrame(export_rows); csvdata=df.to_csv(index=False).encode("utf-8-sig"); jsondata=json.dumps(results,ensure_ascii=False,indent=2).encode()
        col1,col2,col3,col4=st.columns(4)
        xlsx=excel_bytes(df); pdf=pdf_bytes(run,results)
        col1.download_button("Download CSV",csvdata,f"run-{rid}.csv","text/csv")
        if xlsx: col2.download_button("Download Excel",xlsx,f"run-{rid}.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else: col2.caption("Install openpyxl for Excel export.")
        col3.download_button("Download JSON",jsondata,f"run-{rid}.json","application/json")
        if pdf: col4.download_button("Download PDF",pdf,f"run-{rid}.pdf","application/pdf")
        else: col4.caption("Install reportlab for PDF export.")
    else: st.info("No saved runs yet.")

with tab_library:
    st.subheader("Scenario library")
    st.write("Built-in categories cover commerce, shipment, refunds, account support, general service, and prompt injection. Hindi, English, and Hinglish examples are included. These are starter cases; adapt policies and reference answers to your organization before benchmarking.")
    for s in SCENARIOS:
        with st.expander(f"{s['id']} · {s['category']} · {s['language']}"):
            st.markdown(f"**Customer**\n\n{s['customer']}\n\n**Policy context**\n\n{s['policy']}\n\n**Reference answer**\n\n{s['reference_answer']}")

