import React from 'react';
import {Player} from '@remotion/player';
import {HistoryComposition, type HistoryProps} from './HistoryComposition';
export const HistoricalPlayer:React.FC<HistoryProps>=props => <Player component={HistoryComposition} inputProps={props} compositionWidth={1920} compositionHeight={1080} fps={30} durationInFrames={props.timeline.total_frames} controls />;
