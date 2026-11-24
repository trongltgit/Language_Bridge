const {JSDOM,VirtualConsole}=require("jsdom");const {execSync}=require("child_process");const B="http://127.0.0.1:8765";const sleep=ms=>new Promise(r=>setTimeout(r,ms));const errs=[];
async function win(){const vc=new VirtualConsole();vc.on("jsdomError",e=>errs.push(e.message));const d=await JSDOM.fromURL(B+"/",{runScripts:"dangerously",resources:"usable",pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){w.fetch=(u,o)=>fetch(new URL(u,B).href,o);w.alert=()=>{};w.confirm=()=>true;w.HTMLElement.prototype.scrollIntoView=()=>{}}});await sleep(500);const W=d.window;
 return new Proxy(W,{get(t,p){if(p==='then')return undefined;const v=Reflect.get(t,p,t);if(v!==undefined||typeof p!=='string')return typeof v==='function'?v.bind(t):v;return(...a)=>t.eval(`${p}(${a.map(x=>JSON.stringify(x)).join(',')})`)}})}
const set=(w,id,v)=>{w.document.getElementById(id).value=v},txt=w=>w.document.body.textContent.replace(/\s+/g," "),ok=(c,m)=>{console.log((c?"PASS ":"FAIL ")+m);if(!c)process.exitCode=1};
const J=async(p,o={},tok)=>{const r=await fetch(B+p,{method:o.method||(o.body?"POST":"GET"),headers:{...(o.body&&!(o.body instanceof FormData)?{"Content-Type":"application/json"}:{}),...(tok?{Authorization:"Bearer "+tok}:{})},body:o.body instanceof FormData?o.body:o.body&&JSON.stringify(o.body)});return r.json()};
(async()=>{
 const adm=(await J("/auth/login",{body:{email:"admin@example.com",password:"admin-password-123"}})).access_token;
 const u=await J("/admin/users",{body:{name:"Lan",email:"lan@x.com",role:"user"}},adm),t=await J("/admin/users",{body:{name:"Minh",email:"minh@x.com",role:"translator",pairs:["vi-en"],domains:["General"]}},adm);
 await J("/auth/accept-invite",{body:{token:u.invite_token,password:"user-password-123"}});const sec=(await J("/auth/accept-invite",{body:{token:t.invite_token,password:"translator-pass-123"}})).mfa_secret;
 const otp=()=>execSync(`python3 -c "import pyotp;print(pyotp.TOTP('${sec}').now())"`).toString().trim();
 const ut=(await J("/auth/login",{body:{email:"lan@x.com",password:"user-password-123"}})).access_token;await J("/billing/subscribe?plan=Basic",{method:"POST"},ut);
 const fd=new FormData();fd.append("pair_id","vi-en");fd.append("domain","General");fd.append("rush","false");fd.append("file",new Blob(["Sinh ngày 12/03/2015 tại Hà Nội"]),"a.txt");const j=await J("/jobs",{body:fd},ut);await J(`/jobs/${j.id}/pay`,{method:"POST"},ut);
 // translator UI
 let t1=await win();set(t1,"em","minh@x.com");set(t1,"pw","translator-pass-123");set(t1,"otp",otp());t1.doLogin();await sleep(1000);
 ok(txt(t1).includes("Accept")&&txt(t1).includes("you earn")||txt(t1).includes("Job queue"),"translator queue lists the paid job");ok(/\$[\d.]+ − \$[\d.]+ = /.test(txt(t1)),"queue shows value, fee and net before accepting");
 t1.acceptJob(j.id);await sleep(1000);ok(!!t1.document.getElementById("ft"),"editor opens with source and AI draft");
 set(t1,"ft","Born 12/03/2015 in Hanoi");t1.qaJob(j.id);await sleep(900);ok(txt(t1).includes("QA passed"),"QA passes after translator edit");
 t1.approveJob(j.id);await sleep(1200);ok(txt(t1).includes("Job queue"),"translator approves");
 // user UI
 let u1=await win();set(u1,"em","lan@x.com");set(u1,"pw","user-password-123");u1.doLogin();await sleep(900);u1.tab("jobs");await sleep(700);ok(txt(u1).includes("APPROVED"),"user sees APPROVED status");
 u1.getRes(j.id);await sleep(800);ok(txt(u1).includes("Born 12/03/2015 in Hanoi")&&txt(u1).includes("AI-generated"),"user gets result with AI notice");
 console.log("Browser errors:",errs.length?errs:"none")})();
