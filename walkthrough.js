const {JSDOM,VirtualConsole}=require("jsdom");const B="http://127.0.0.1:8765";const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const errs=[];
async function win(){const vc=new VirtualConsole();vc.on("jsdomError",e=>errs.push("jsdomError: "+e.message));vc.on("error",e=>errs.push("console.error: "+e));
 const d=await JSDOM.fromURL(B+"/",{runScripts:"dangerously",resources:"usable",pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){w.fetch=(u,o)=>fetch(new URL(u,B).href,o);w.alert=()=>{};w.confirm=()=>true;w.WebSocket=require("ws");w.HTMLElement.prototype.scrollIntoView=()=>{}}});
 await sleep(500);const W=d.window;return new Proxy(W,{get(t,p){if(p==='then')return undefined;const v=Reflect.get(t,p,t);if(v!==undefined||typeof p!=='string')return typeof v==='function'?v.bind(t):v;return (...a)=>t.eval(`${p}(${a.map(x=>JSON.stringify(x)).join(',')})`)}})}
const set=(w,id,v)=>{w.document.getElementById(id).value=v};const txt=w=>w.document.body.textContent.replace(/\s+/g," ");
const ok=(c,m)=>{console.log((c?"PASS ":"FAIL ")+m);if(!c)process.exitCode=1};
async function login(email,pw,otp=""){const w=await win();set(w,"em",email);set(w,"pw",pw);set(w,"otp",otp);w.doLogin();await sleep(900);return w}
(async()=>{
 // ADMIN
 let a=await login("admin@example.com","admin-password-123");ok(txt(a).includes("Accounts")&&txt(a).includes("Platform Admin"),"admin signs in and sees Accounts");
 set(a,"nn","Lan Nguyen");set(a,"ne","lan@x.com");set(a,"nr","user");a.mkUser();await sleep(700);const uInv=a.document.querySelector("#inv pre").textContent.split("/invite/")[1];ok(!!uInv,"admin creates user and gets invite link");
 set(a,"nn","Minh Tran");set(a,"ne","minh@x.com");set(a,"nr","translator");set(a,"np2","vi-en");set(a,"nd","General");a.mkUser();await sleep(700);const tInv=a.document.querySelector("#inv pre").textContent.split("/invite/")[1];ok(!!tInv,"admin creates translator and gets invite link");
 for(const k of ["creds","pricing","ledger","audit","tools"]){a.tab(k);await sleep(500);ok(txt(a).length>200&&!txt(a).includes("undefined"),"admin tab renders: "+k)}
 a.tab("audit");await sleep(500);ok(txt(a).includes("create_user"),"audit log records account creation");
 // USER accepts invite via UI
 let g=await win();g.location.hash="#/invite/"+uInv;await sleep(400);ok(g.document.getElementById("tk").value===uInv,"invite link prefills the code");set(g,"np","user-password-123");g.doInvite();await sleep(700);
 // TRANSLATOR accepts invite and gets MFA secret
 let g2=await win();set(g2,"tk",tInv);set(g2,"np","translator-pass-123");g2.doInvite();await sleep(800);const sec=g2.document.querySelector("#mfa pre")?.textContent.trim();ok(!!sec,"translator receives an MFA secret");
 const {authenticator}=(()=>{try{return require("otplib")}catch(e){return{}}})();
 const otp=require("child_process").execSync(`python3 -c "import pyotp;print(pyotp.TOTP('${sec}').now())"`).toString().trim();
 // USER flow
 let u=await login("lan@x.com","user-password-123");ok(txt(u).includes("Subscribe"),"user sees plans");u.subscribe("Pro");await sleep(800);ok(txt(u).includes("Subscription active"),"user subscribes");
 u.tab("new");await sleep(500);ok(u.document.getElementById("fl")!=null,"upload form renders");
 u.tab("book");await sleep(900);ok(txt(u).includes("Rules for this case"),"booking shows policy rules");
 set(u,"dm","General");u.document.getElementById("c1").checked=true;u.document.getElementById("c2").checked=true;u.startSess();await sleep(1500);ok(txt(u).includes("Billing starts when all three"),"live room opens for the user");
 // find session + guest link via API
 const tok=u.sessionStorage.getItem("tok");const sess=await (await fetch(B+"/sessions",{headers:{Authorization:"Bearer "+tok}})).json();const S=sess[0];ok(S&&S.guest_link_token,"session lists a guest link");
 // TRANSLATOR joins
 let t=await login("minh@x.com","translator-pass-123",otp);ok(txt(t).includes("Job queue"),"translator signs in with MFA code");
 t.tab("live");await sleep(600);ok(txt(t).includes("Open"),"translator sees the open session");
 await fetch(B+"/sessions/"+S.id+"/join",{method:"POST",headers:{"Content-Type":"application/json",Authorization:"Bearer "+t.sessionStorage.getItem("tok")},body:JSON.stringify({consent:true})});
 t.enter(S.id);await sleep(900);ok(txt(t).includes("Private AI assist"),"translator live room shows assist panel");
 // GUEST via link
 let gu=await win();gu.location.hash=`#/join/${S.id}/${S.guest_link_token}`;await sleep(900);ok(txt(gu).includes("No account needed"),"guest link page loads");gu.document.getElementById("gc").checked=true;gu.guestJoin(S.id,S.guest_link_token);await sleep(1200);ok(gu.document.getElementById("caps")!=null,"guest enters live room");
 await sleep(3500);ok(txt(u).includes("connected"),"tiles show connected participants");
 set(u,"tx","Tôi bị đau 2 ngày");u.document.getElementById("sl").value="vi";u.sendLive();await sleep(1200);
 ok(txt(gu).includes("Tôi bị đau"),"caption from user reaches guest");ok(txt(t).includes("Tôi bị đau"),"caption reaches translator");
 u.endLive();await sleep(1200);ok(txt(u).includes("Sessions"),"user ends session");
 const led=await (await fetch(B+"/admin/ledger",{headers:{Authorization:"Bearer "+a.sessionStorage.getItem("tok")}})).json();ok(led.some(x=>x.type==="COMMISSION"),"commission posted for the session");
 console.log("\nBrowser-side errors:",errs.length?errs:"none");process.exit(process.exitCode||0)})();
