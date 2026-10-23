import React from 'react';
import {Player} from '@remotion/player';
import {HistoryComposition,type HistoryProps} from './HistoryComposition';
import {assertMedia,assertTimeline,fail} from './schema';

/** B2-01 same-process host capability. This object cannot be minted from raw browser props. */
const issued=new WeakMap<object,HistoryProps>();
/** Snapshot only JSON-like verified timeline/media data, then freeze every descendant.
 * Do not retain aliases into the resolver's mutable return object.
 */
function immutableHostSnapshot(source:HistoryProps):HistoryProps{
 const snapshot=structuredClone(source);
 const seen=new WeakSet<object>();
 const freeze=(value:unknown):void=>{
  if(value===null||typeof value!=='object'||seen.has(value))return;
  seen.add(value);
  for(const child of Object.values(value))freeze(child);
  Object.freeze(value);
 };
 freeze(snapshot);
 return snapshot;
}
export type PreparedHistoryPlayer=Readonly<{readonly props:Readonly<HistoryProps>}>;
/** Only the native trusted SQLite project exporter may issue this capability.
 * Browser serialization and the production Player host UI are B2-05; a
 * deserialized object must fail closed instead of trusting a claimed G4 SHA.
 */
export async function prepareApprovedPlayerOnLocalHost(
 sqlite:string,artifactRoot:string,project:string):Promise<PreparedHistoryPlayer>{
 if(typeof process==='undefined'||process.platform!=='win32')
  fail('PLAYER_HOST_REQUIRED',project,'Approved preparation requires the Windows project host');
 const {prepareApprovedLocalHistory}=await import('../scripts/approved-host');
 const props=prepareApprovedLocalHistory(sqlite,artifactRoot,project);
 assertTimeline(props.timeline);
 assertMedia(props.timeline,props.media);
 if(props.media.sourceKind!=='APPROVED_LOCAL')
  fail('PLAYER_SYNTHETIC_UNTRUSTED',project,'Fixture cannot issue an approved Player');
 const snapshot=immutableHostSnapshot(props);
 const prepared=Object.freeze({props:snapshot});
 issued.set(prepared,snapshot);
 return prepared;
}
/** The public mount does NOT accept {timeline, media} or a caller-declared G4 hash. */
export const HistoricalPlayer:React.FC<{prepared:PreparedHistoryPlayer}>=({prepared})=>{
 const props=prepared&&issued.get(prepared);
 if(!props)
  fail('PLAYER_UNTRUSTED_PROPS','Player','Host must verify the current SQLite G4 head and local bytes before mounting');
 return <Player component={HistoryComposition} inputProps={props} compositionWidth={1920}
  compositionHeight={1080} fps={30} durationInFrames={props.timeline.total_frames} controls />;
};
/** Synthetic test harness only. Never mount as an approved operator Player. */
export const SyntheticPlayerTestOnly:React.FC<HistoryProps>=props=>{
 if(props.media.sourceKind!=='SYNTHETIC')fail('PLAYER_TEST_ONLY',props.timeline.project_id,'Use trusted host for approved media');
 return <Player component={HistoryComposition} inputProps={props} compositionWidth={1920}
  compositionHeight={1080} fps={30} durationInFrames={props.timeline.total_frames} controls />;
};
