import {useEffect,useState} from "react";
import {assetApi,type ProviderInfo} from "../../api/assets";
export function ProviderSettings() {
  const [providers,setProviders]=useState<ProviderInfo[]>([]);
  const [provider,setProvider]=useState("europeana");
  const [key,setKey]=useState("");
  const [base,setBase]=useState("http://127.0.0.1:8765");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const [confirmClear,setConfirmClear]=useState(false);
  async function refresh(){setProviders((await assetApi.providers()).providers);}
  useEffect(()=>{void refresh().catch(e=>setError(String(e)));},[]);
  async function save(clear=false){
    setBusy(true);setError("");setMessage("");
    try{
      const result=await assetApi.settings(provider,clear?undefined:key||undefined,provider==="glabs_webhook"?base:"",clear);
      setMessage(result.configured?"Provider configured locally; live connectivity NOT_RUN.":"Credential explicitly cleared; live connectivity NOT_RUN.");
      setKey("");setConfirmClear(false);await refresh();
    }catch(e){setError(String(e));}finally{setBusy(false);}
  }
  return <section className="panel">
    <h3>Provider settings (local only)</h3>
    <p>Keys are never read back in API responses. A configured key is not a successful live test.</p>
    <ul>{providers.map(x=><li key={x.provider}>{x.provider}: {x.configured?"Configured":"Not configured"} · live {x.live_status}</li>)}</ul>
    <label htmlFor="asset-provider">Provider</label>
    <select id="asset-provider" value={provider} onChange={e=>{setProvider(e.target.value);setConfirmClear(false);}}>
      <option value="europeana">Europeana</option><option value="glabs_webhook">G-Labs webhook</option>
    </select>
    {provider==="glabs_webhook" && <><label htmlFor="asset-base">Local URL</label><input id="asset-base" value={base} onChange={e=>setBase(e.target.value)}/></>}
    <label htmlFor="asset-secret">Provider key (never shown after saving)</label>
    <input id="asset-secret" type="password" autoComplete="off" value={key} onChange={e=>setKey(e.target.value)}/>
    <button disabled={busy} onClick={()=>void save()}>{busy?"Saving…":"Save settings (blank key keeps current)"}</button>
    <button disabled={busy} onClick={()=>setConfirmClear(true)}>Clear saved credential…</button>
    {confirmClear&&<div role="group" aria-label="Confirm credential clear">
      <p>Remove the local provider key? Pending jobs may need the original key restored.</p>
      <button disabled={busy} onClick={()=>void save(true)}>Confirm clear credential</button>
      <button disabled={busy} onClick={()=>setConfirmClear(false)}>Keep credential</button>
    </div>}
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
  </section>;
}
