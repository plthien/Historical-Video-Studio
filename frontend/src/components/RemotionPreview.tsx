/** Browser-only G4 DRAFT preview. This accepts a host-delivered view, NEVER a Node
 * player capability. Node renderer accepts only prepareApprovedPlayerOnLocalHost's
 * private identity token; serializing this snapshot cannot mint one.
 */
import {useEffect, useRef, useState} from 'react';
import {Player, type PlayerRef} from '@remotion/player';
import {HistoryComposition, type HistoryProps} from '../../../renderer/remotion/HistoryComposition';
import {assertTimeline,assertMedia} from '../../../renderer/remotion/schema';

export function RemotionPreview({props,frame}: {props:HistoryProps;frame:number}) {
  const player=useRef<PlayerRef>(null);
  const [seek,setSeek]=useState(frame);
  assertTimeline(props.timeline);
  assertMedia(props.timeline,props.media);
  useEffect(()=>{setSeek(frame);player.current?.seekTo(Math.min(props.timeline.total_frames-1,Math.max(0,frame)));},
    [frame,props.timeline]);
  return <section aria-label="Read-only local Remotion Player" className="panel">
    <p><strong>G4 DRAFT · VIEW ONLY</strong> — not operator approval or final Node render authority.</p>
    <label htmlFor="g4-seek">Seek exact frame (30 fps)</label>
    <input id="g4-seek" aria-label="Seek exact frame" type="number" min={0} max={props.timeline.total_frames-1}
       value={seek} onChange={e=>{
         const target=Math.max(0,Math.min(props.timeline.total_frames-1,Number(e.target.value)||0));
         setSeek(target);player.current?.seekTo(target);
       }}/>
    <div data-testid="player-stage" style={{width:'100%',aspectRatio:'16 / 9'}}>
    <Player ref={player} component={HistoryComposition} inputProps={props}
      fps={30} compositionWidth={1920} compositionHeight={1080}
      durationInFrames={props.timeline.total_frames} autoPlay={false}
      controls style={{width:'100%',aspectRatio:'16 / 9'}}/>
    </div>
  </section>;
}
