/** Browser-only G4 DRAFT preview. This accepts a host-delivered view, NEVER a Node
 * player capability. Node renderer accepts only prepareApprovedPlayerOnLocalHost's
 * private identity token; serializing this snapshot cannot mint one.
 */
import {useEffect, useRef} from 'react';
import {Player, type PlayerRef} from '@remotion/player';
import {HistoryComposition, type HistoryProps} from '../../../renderer/remotion/HistoryComposition';
import {assertTimeline,assertMedia} from '../../../renderer/remotion/schema';

export function RemotionPreview({props,frame}: {props:HistoryProps;frame:number}) {
  const player=useRef<PlayerRef>(null);
  assertTimeline(props.timeline);
  assertMedia(props.timeline,props.media);
  useEffect(()=>{player.current?.seekTo(Math.min(props.timeline.total_frames-1,Math.max(0,frame)));},
    [frame,props.timeline]);
  return <section aria-label="Read-only local Remotion Player" className="panel">
    <p><strong>G4 DRAFT · VIEW ONLY</strong> — not operator approval or final Node render authority.</p>
    <Player ref={player} component={HistoryComposition} inputProps={props}
      fps={30} compositionWidth={1920} compositionHeight={1080}
      durationInFrames={props.timeline.total_frames} autoPlay={false}
      controls style={{width:'100%',aspectRatio:'16 / 9'}}/>
  </section>;
}
