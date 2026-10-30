import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequestScope} from '../apps/web/request-scope-core.mjs';

test('a response from the previous workspace cannot restore private state',async()=>{
 const scope=createRequestScope();let resolve;let state={owner:'previous'};
 const response=new Promise(r=>{resolve=r;});const ticket=scope.capture();
 const pending=(async()=>{const value=await response;if(scope.current(ticket))state=value;})();
 scope.invalidate();state={owner:'new'};resolve({owner:'previous',privateScene:'old'});await pending;
 assert.deepEqual(state,{owner:'new'});
});
test('current workspace results remain usable and invalidations are monotonic',()=>{
 const scope=createRequestScope(),ticket=scope.capture();assert.equal(scope.current(ticket),true);
 scope.invalidate();scope.invalidate();assert.equal(scope.current(ticket),false);
 assert.equal(scope.current(scope.capture()),true);
});
