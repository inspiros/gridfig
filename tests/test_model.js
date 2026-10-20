const {test} = require('node:test');
const assert = require('node:assert/strict');
const M = require('../web/model.js');

test('unit changes preserve physical lengths, including CSS pixels at 96ppi', () => {
  assert.equal(M.toMM(1,'in'),25.4);
  assert.equal(M.toMM(72,'pt'),25.4);
  assert.equal(M.toMM(96,'px'),25.4);
  for(const unit of Object.keys(M.mmPerUnit)) assert.ok(Math.abs(M.toMM(M.fromMM(36,unit),unit)-36)<1e-10);
});
test('zero margin and gaps align the arrangement with a 124 by 94mm PDF', () => {
  const g=M.geometry({images:[[1,2,3],[4,5,6]],headers:{top:['a','b','c'],left:['a','b'],bottom:['a','b','c']},layout:{cell_width_mm:36,cell_height_mm:36,gap_mm:0,header_gap_mm:2,side_width_mm:14,margin_mm:0,top_height_mm:12,bottom_height_mm:6,font_size_pt:10}});
  assert.equal(g.width,124);assert.equal(g.height,94);
  const first=g.regions.find(r=>r.kind==='image');
  assert.equal(first.x,16);assert.equal(first.y,14);
  const top=g.regions.find(r=>r.side==='top');assert.equal(top.y,0);assert.equal(top.h,12);
});
test('method folders align matching sample stems, with natural ordering and holes', () => {
  const p=M.methodFolderPlan(['results/ours/scene10.png','results/baseline/scene2.jpg','results/ours/scene2.webp']);
  assert.deepEqual(p.methods,['baseline','ours']);assert.deepEqual(p.samples,['scene2','scene10']);
  assert.deepEqual(p.matrix,[[1,2],[null,0]]);
});
test('ambiguous duplicate stems and nested method layouts are rejected', () => {
  assert.throws(()=>M.methodFolderPlan(['root/ours/scene.png','root/ours/scene.jpg']),/Duplicate/);
  assert.throws(()=>M.methodFolderPlan(['root/ours/nested/scene.png']),/method\/sample/);
});
test('flat import ordering places scene2 before scene10', () => {
  assert.deepEqual(['scene10.png','scene2.png','scene1.png'].sort(M.natural),['scene1.png','scene2.png','scene10.png']);
});
test('Tight removes margins and gaps but preserves image sizes, fonts and labels', () => {
  const original={margin_mm:9,gap_mm:7,header_gap_mm:6,top_height_mm:12,bottom_height_mm:9,cell_width_mm:36,cell_height_mm:24,font_size_pt:11,side_width_mm:14,rotations:{left:90}};
  const tight=M.presetLayout(original,'tight');
  assert.equal(tight.margin_mm,0);assert.equal(tight.gap_mm,0);assert.equal(tight.header_gap_mm,0);
  assert.equal(tight.top_height_mm,null);assert.equal(tight.bottom_height_mm,null);
  assert.equal(tight.cell_width_mm,36);assert.equal(tight.cell_height_mm,24);assert.equal(tight.font_size_pt,11);assert.equal(tight.rotations.left,90);
  assert.equal(original.margin_mm,9);assert.equal(M.matchingPreset(tight),'tight');
  assert.equal(M.matchingPreset({...tight,gap_mm:1}),'custom');
});
test('Paper and Airy can be restored from Tight without changing cell dimensions', () => {
  const tight=M.presetLayout({cell_width_mm:30},'tight');
  for(const name of ['paper','airy']){
    const layout=M.presetLayout(tight,name);
    assert.equal(M.matchingPreset(layout),name);assert.equal(layout.cell_width_mm,30);
    assert.ok(layout.margin_mm>0);assert.ok(layout.gap_mm>0);assert.ok(layout.header_gap_mm>0);
  }
});
test('extra imports go to the tray rather than being dropped when a grid is full', () => {
  const state={images:[['a',null]],tray:['unused']};
  const next=M.placeImports(state,['b','c','d']);
  assert.deepEqual(next.images,[['a','b']]);assert.deepEqual(next.tray,['unused','c','d']);
  assert.deepEqual(state.images,[['a',null]]);
  assert.deepEqual(M.placeImports(next,['e']).tray,['unused','c','d','e']);
});
test('tray placement swaps the displaced image back into the tray', () => {
  const state={images:[['a','b']],tray:['c','d']};
  const next=M.moveImage(state,{kind:'tray',index:0},{kind:'grid',r:0,c:1});
  assert.deepEqual(next.images,[['a','c']]);assert.deepEqual(next.tray,['b','d']);
});
test('grid images move to the tray, tray cards reorder, and clicking can place into empty cells', () => {
  const state={images:[['a','b']],tray:['c','d']};
  const moved=M.moveImage(state,{kind:'grid',r:0,c:0},{kind:'tray'});
  assert.deepEqual(moved.images,[[null,'b']]);assert.deepEqual(moved.tray,['c','d','a']);
  const reordered=M.moveImage(moved,{kind:'tray',index:2},{kind:'tray',index:0});
  assert.deepEqual(reordered.tray,['a','c','d']);
  const placed=M.moveImage(reordered,{kind:'tray',index:0},{kind:'grid',r:0,c:0});
  assert.deepEqual(placed.images,[['a','b']]);assert.deepEqual(placed.tray,['c','d']);
});
test('clear all empties the grid and tray while setting images aside retains all of them', () => {
  const state={images:[['a','b'],[null,'c']],tray:['d']};
  const aside=M.gridToTray(state);
  assert.deepEqual(aside.images,[[null,null],[null,null]]);assert.deepEqual(aside.tray,['d','a','b','c']);
  assert.deepEqual(M.clearImages(state),{images:[[null,null],[null,null]],tray:[]});
});
test('replacement imports keep old cells in the tray and only-tray imports preserve the figure', () => {
  const state={images:[['a','b']],tray:[]};
  assert.deepEqual(M.placeImports(state,['c'],[0,0]),{images:[['c','b']],tray:['a']});
  assert.deepEqual(M.placeImports(state,['c'],null,true),{images:[['a','b']],tray:['c']});
});
