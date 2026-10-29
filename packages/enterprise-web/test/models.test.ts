import {test} from 'node:test';import assert from 'node:assert/strict';
import {modelCapabilities,reviewedCatalog,prepareModelRequest,FREE_CHAT_MODELS} from '../src/models.ts';
const site='semiconductor-yield-timing-platform';
const table={columns:[{name:'temperature',dtype:'float64'},{name:'process',dtype:'string'}],target:'yield',context:[[20,'A',.8],[30,'B',.7]],predict:[[25,'A']]};
test('applicability reflects product workloads; scientific adapters remain external',()=>{
 assert.equal(modelCapabilities('agent-tool-permission-firewall').length,1);assert.equal(modelCapabilities(site).length,2);
 assert.equal(modelCapabilities('chemistry-materials-provenance-platform').length,3);assert.equal(reviewedCatalog().length,4);
 assert.throws(()=>prepareModelRequest(site,{model:'ipd/rfd4-proteina'}),/not_applicable/);
 assert.throws(()=>prepareModelRequest('chemistry-materials-provenance-platform',{model:'ipd/rfd4-proteina'}),/dedicated_scientific/);
 assert.ok(reviewedCatalog().find(m=>m.task==='quantum_calibration')!.limitation.includes('does not simulate'));
});
test('reasoning payload is bounded, credential-free and explicitly not executed',()=>{
 const p=prepareModelRequest(site,{model:FREE_CHAT_MODELS[0],prompt:' Explain uncertainty. '});
 assert.equal(p.status,'prepared_not_executed');assert.equal(p.url,'https://integrate.api.nvidia.com/v1/chat/completions');
 assert.equal(p.body.stream,false);assert.equal(p.body.max_tokens,1024);assert.equal(p.headers.Authorization,'Bearer ${NVIDIA_API_KEY}');
 assert.equal((p.body.messages as {content:string}[])[1].content,'Explain uncertainty.');
 for(const prompt of ['',null,4,'x'.repeat(4001)])assert.throws(()=>prepareModelRequest(site,{model:FREE_CHAT_MODELS[0],prompt}));
 assert.throws(()=>prepareModelRequest(site,{model:FREE_CHAT_MODELS[0],prompt:'hi',table}),/table_not_supported/);
});
test('tabular target labels stay out of predictions and row IDs are disjoint',()=>{
 const p=prepareModelRequest(site,{model:'nvidia/kumo-tabular',table}),b=p.body as Record<string,any>;
 assert.equal(p.url,'https://ai.api.nvidia.com/v1/structured-data/nvidia/kumo-tabular/predictions');
 assert.deepEqual(b.context.instance_table.columns,['row_id','temperature','process','yield']);
 assert.deepEqual(b.predict.instance_table.columns,['row_id','temperature','process']);
 assert.deepEqual(b.predict.instance_table.rows,[['predict-0',25,'A']]);assert.equal(b.context.instance_table.rows[0][0],'context-0');
 assert.deepEqual(b.output.fields,['prediction']);assert.deepEqual(table.predict,[[25,'A']]);
 const nullable=structuredClone(table) as any;nullable.context[0][0]=null;nullable.predict[0][1]=null;
 assert.doesNotThrow(()=>prepareModelRequest(site,{model:'nvidia/kumo-tabular',table:nullable}));
});
test('ambiguous, malicious and oversized requests fail before submission',()=>{
 const attempts=[null,{}, {columns:[]}, {...table,columns:Array(25).fill(table.columns[0])},
  {...table,columns:[{name:'__proto__',dtype:'string'}]}, {...table,columns:[{name:'x',dtype:'int32'}]},
  {...table,columns:[table.columns[0],table.columns[0]]}, {...table,target:'temperature'}, {...table,target:'__proto__'},
  {...table,context:[[20,'A',Infinity],[25,'B',1]]}, {...table,context:[[20,'A','bad'],[25,'B',1]]},
  {...table,context:[[20,'A',1]]},{...table,context:Array(201).fill([20,'A',1])},
  {...table,predict:[[2]]},{...table,predict:[['wrong','A']]},{...table,predict:[[1,7]]},
  {...table,predict:[[2,'x'.repeat(257)]]},{...table,predict:[[2,'bad\ncell']]},{...table,predict:[[2,{}]]},
  {...table,extra:'field'},{...table,columns:[{name:'temperature',dtype:'float64',extra:true}]}];
 for(const bad of attempts)assert.throws(()=>prepareModelRequest(site,{model:'nvidia/kumo-tabular',table:bad}));
 for(const raw of [null,[],true,{model:'evil'},{model:'nvidia/kumo-tabular',prompt:'text',table},
  {model:'nvidia/kumo-tabular',table,url:'http://localhost'}])assert.throws(()=>prepareModelRequest(site,raw));
});
