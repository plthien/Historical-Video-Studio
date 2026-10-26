/** B2-05 native Windows view-only snapshot issuer. Never accepts browser-supplied props. */
import {prepareApprovedLocalHistory} from './approved-host';
import {assertMedia,assertTimeline} from '../remotion/schema';
const [sqlite,root,project]=process.argv.slice(2);
if(process.platform!=='win32'||!sqlite||!root||!project)throw Error('PLAYER_HOST_REQUIRED');
const props=prepareApprovedLocalHistory(sqlite,root,project);
assertTimeline(props.timeline);
assertMedia(props.timeline,props.media);
if(props.media.sourceKind!=='APPROVED_LOCAL')throw Error('PLAYER_SOURCE_NOT_APPROVED');
process.stdout.write(JSON.stringify(props));
