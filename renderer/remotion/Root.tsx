import React from 'react';
import {Composition} from 'remotion';
import {HistoryComposition, type HistoryProps} from './HistoryComposition';
export const COMPOSITION_ID='HistoricalTimelineV1';
export const Root: React.FC=()=> <Composition id={COMPOSITION_ID} component={HistoryComposition} width={1920} height={1080} fps={30} durationInFrames={180} defaultProps={{timeline: null,media: null} as unknown as HistoryProps} calculateMetadata={({props})=>({durationInFrames: props.timeline?.total_frames ?? 180})}/>;
