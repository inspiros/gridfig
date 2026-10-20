"use strict";
const $ = id => document.getElementById(id);
const M = GridfigModel;
const sides = ["top", "left", "bottom", "right"];
const defaults = {cell_width_mm:36,cell_height_mm:36,gap_mm:1.5,header_gap_mm:2,side_width_mm:14,top_height_mm:8,bottom_height_mm:6,font_size_pt:10,font:"Libertinus Serif",fit:"contain",stroke_pt:0,margin_mm:2,rotations:{}};
const layoutKeys = Object.keys(defaults).filter(key => key !== "rotations");
let config, assets = {}, labels = {}, urls = new Map(), targetCell = null;
let fileDestination = "grid";
let revision = 0, busy = false, dirty = false, lastPreview = -1;
let previewTimer = null, pendingPreview = false, renderedWidthMm = null;
const nullable = key => key === "top_height_mm" || key === "bottom_height_mm";
const pretty = number => Number(number.toFixed(6)).toString();

function error(message) { $("error").hidden = !message; $("error").textContent = message || ""; }
function changed(figureChanged=true) {
  dirty = true;
  if(!figureChanged){$("status").textContent="Image tray updated · unused images are excluded from the PDF";return;}
  revision++;
  $("status").textContent = $("preview-pane").hidden ? "Arrangement updated · open PDF preview for final typesetting" : "Your edits will appear in the PDF preview automatically…";
  applyLayout();
  $("preset").value=M.matchingPreset(config.layout);
  if (!$("preview-pane").hidden) queuePreview();
}
function previewPending(message="Updating preview…") {
  $("preview-state").textContent=message;$("preview-state").hidden=false;
  $("preview").classList.add("outdated");
}
function queuePreview(delay=450) {
  clearTimeout(previewTimer);
  if ($("preview-pane").hidden) { pendingPreview=false; return; }
  pendingPreview=true;previewPending();
  previewTimer=setTimeout(()=>{previewTimer=null;run("preview");},delay);
}
function labelString(value) { return typeof value === "object" && value !== null ? "=" + value.typst : (value || ""); }
function labelValue(value) { return value.startsWith("=") ? {typst:value.slice(1)} : value; }
function syncHeaders() {
  for (const side of sides) {
    if ($("side-" + side).checked) config.headers[side] = labels[side];
    else delete config.headers[side];
  }
}
function mime(name) {
  return {jpg:"image/jpeg",jpeg:"image/jpeg",svg:"image/svg+xml",png:"image/png",webp:"image/webp",gif:"image/gif"}[name.split(".").pop().toLowerCase()] || "application/octet-stream";
}
function bytes(encoded) { return Uint8Array.from(atob(encoded), ch => ch.charCodeAt(0)); }
function assetURL(name) {
  if (!urls.has(name)) urls.set(name, URL.createObjectURL(new Blob([bytes(assets[name])], {type:mime(name)})));
  return urls.get(name);
}
function view(name) {
  $("edit-pane").hidden = name !== "edit"; $("preview-pane").hidden = name === "edit";
  for (const key of ["edit", "preview"]) {
    $(key + "-tab").classList.toggle("active", key === name);
    $(key + "-tab").setAttribute("aria-selected", String(key === name));
  }
  if(name==="edit") { clearTimeout(previewTimer);previewTimer=null;pendingPreview=false; }
  else if(lastPreview!==revision) previewPending();
}
function unitFor(key) { return key.endsWith("_mm") ? $("length-unit").value : $("type-unit").value; }
function toDisplay(key, value) {
  const mm = key.endsWith("_pt") ? M.toMM(value,"pt") : value;
  return M.fromMM(mm,unitFor(key));
}
function fromDisplay(key, value) {
  const mm = M.toMM(value,unitFor(key));
  return key.endsWith("_pt") ? M.fromMM(mm,"pt") : mm;
}
function updateUnitControls() {
  for (const key of layoutKeys) {
    const input = $(key);
    if (!key.endsWith("_mm") && !key.endsWith("_pt")) { input.value=config.layout[key]; continue; }
    input.closest("label").querySelector("span").textContent=unitFor(key);
    input.value=config.layout[key] == null ? "" : pretty(toDisplay(key,config.layout[key]));
    input.min=pretty(toDisplay(key,Number(input.dataset.baseMin)));
    input.max=pretty(toDisplay(key,Number(input.dataset.baseMax)));
    input.step="any";
  }
}
function applyLayout() {
  if (!config) return;
  const g=M.geometry(config), l=config.layout;
  if (![g.width,g.height].every(v=>Number.isFinite(v) && v>0) || l.cell_width_mm<=0 || l.cell_height_mm<=0) return;
  const available=Math.max(200,document.querySelector(".canvas").clientWidth-48);
  const zoom=$("zoom").value === "fit" ? Math.min(1,available/(g.width*96/25.4)) : Number($("zoom").value);
  const scale=96/25.4*zoom;
  $("paper").style.width=g.width*scale+"px"; $("paper").style.height=g.height*scale+"px";
  // Keep the last raster at its own physical size until its replacement arrives.
  $("preview").style.width=(renderedWidthMm ?? g.width)*scale+"px";
  $("grid").style.fontSize=l.font_size_pt*96/72*zoom+"px";
  $("grid").style.fontFamily=JSON.stringify(l.font)+", serif";
  for (const region of g.regions) {
    const el=$(region.kind === "image" ? `cell-${region.r}-${region.c}` : `header-${region.side}-${region.index}`);
    if (!el) continue;
    Object.assign(el.style,{left:region.x*scale+"px",top:region.y*scale+"px",width:region.w*scale+"px",height:region.h*scale+"px"});
    if(region.kind==="image") {
      el.style.boxShadow=l.stroke_pt>0?`inset 0 0 0 ${l.stroke_pt*96/72*zoom}px #a0a0a0`:"none";
      const img=el.querySelector("img"); if(img) img.style.objectFit=l.fit==="stretch"?"fill":l.fit;
    } else {
      const input=el.querySelector("input"), angle=l.rotations[region.side] || 0;
      const vertical=Math.abs(angle%180)===90;
      input.style.width=(vertical?region.h:region.w)*scale+"px";
      input.style.height=(vertical?region.w:region.h)*scale+"px";
      input.style.transform=`rotate(${-angle}deg)`;
    }
  }
  const unit=$("length-unit").value;
  const auto=["top","bottom"].some(side=>config.headers[side] && l[side+"_height_mm"]==null);
  $("dimensions").textContent=`${config.images.length} × ${config.images[0].length} · ${auto?"≈ ":""}${M.fromMM(g.width,unit).toFixed(2)} × ${M.fromMM(g.height,unit).toFixed(2)} ${unit} · ${Math.round(zoom*100)}%`;
  $("arrangement-note").textContent="Live dimensions · rich labels show source"+(auto?" · Auto header heights estimated":"");
}
function headerCell(side,index) {
  const box=document.createElement("div"),input=document.createElement("input");
  box.id=`header-${side}-${index}`;box.className="header-cell";
  input.value=labelString(labels[side][index]);input.setAttribute("aria-label",`${side} header ${index+1}`);
  input.placeholder=`${side} ${index+1}`;
  input.addEventListener("input",()=>{labels[side][index]=labelValue(input.value);syncHeaders();changed();});
  box.append(input);return box;
}
function pruneAssets() {
  const used=new Set([...config.images.flat().filter(Boolean),...config.tray]);
  for(const name of Object.keys(assets))if(!used.has(name)){
    delete assets[name];if(urls.has(name)){URL.revokeObjectURL(urls.get(name));urls.delete(name);}
  }
}
function dragSource(value) {
  const source=JSON.parse(value);
  return Array.isArray(source)?{kind:"grid",r:source[0],c:source[1]}:source;
}
function applyImages(next,figureChanged=true,showGrid=true) {
  Object.assign(config,next);changed(figureChanged);draw();
  if(showGrid)view("edit");
}
function placeTray(index) {
  for(let r=0;r<config.images.length;r++)for(let c=0;c<config.images[r].length;c++)if(!config.images[r][c]){
    applyImages(M.moveImage(config,{kind:"tray",index},{kind:"grid",r,c}));return;
  }
  error("The grid is full. Drag a tray image onto a cell to swap it, or add more rows/columns.");
}
async function trayDrop(ev,index) {
  ev.preventDefault();ev.stopPropagation();$("tray-list").classList.remove("dragover");
  try {
    const origin=ev.dataTransfer.getData("text/x-gridfig");
    if(origin){const source=dragSource(origin);applyImages(M.moveImage(config,source,{kind:"tray",index}),source.kind==="grid",false);}
    else await addFiles(ev.dataTransfer.files,null,true);
  }catch(e){error(e.message);}
}
function drawTray() {
  const list=$("tray-list");list.replaceChildren();$("tray-count").textContent=`${config.tray.length} unused`;
  if(!config.tray.length){const hint=document.createElement("span");hint.className="tray-empty";hint.textContent="Drop extra images here, or choose Add to tray.";list.append(hint);}
  config.tray.forEach((name,index)=>{
    const item=document.createElement("div");item.className="tray-item";item.draggable=true;item.tabIndex=0;item.setAttribute("role","button");
    item.setAttribute("aria-label",`Place tray image ${index+1}: ${name.split("/").pop()}`);
    const img=document.createElement("img");img.src=assetURL(name);img.alt=name.split("/").pop();img.draggable=false;
    const caption=document.createElement("span");caption.className="tray-caption";caption.textContent=name.split("/").pop().replace(/^[a-f\d-]{36}-/,"");caption.title=name;
    const remove=document.createElement("button");remove.className="tray-remove";remove.textContent="×";remove.title="Remove unused image";
    remove.setAttribute("aria-label",`Remove tray image ${index+1}`);
    remove.onclick=ev=>{ev.stopPropagation();config.tray.splice(index,1);changed(false);draw();};
    item.append(img,caption,remove);item.onclick=()=>{error("");placeTray(index);};
    item.onkeydown=ev=>{if(ev.target===item&&(ev.key==="Enter"||ev.key===" ")){ev.preventDefault();placeTray(index);}};
    item.ondragstart=ev=>ev.dataTransfer.setData("text/x-gridfig",JSON.stringify({kind:"tray",index}));
    item.ondragover=ev=>ev.preventDefault();item.ondrop=ev=>trayDrop(ev,index);list.append(item);
  });
}
function draw() {
  const grid=$("grid");grid.replaceChildren();
  for(const side of sides) if($("side-"+side).checked) labels[side].forEach((_,i)=>grid.append(headerCell(side,i)));
  config.images.forEach((row,r)=>row.forEach((name,c)=>{
    const cell=document.createElement("div");cell.id=`cell-${r}-${c}`;cell.className="tile"+(name?" filled":"");
    cell.tabIndex=0;cell.setAttribute("role","button");
    cell.setAttribute("aria-label",`Row ${r+1}, column ${c+1}${name?": "+name.split("/").pop():": choose image"}`);
    cell.addEventListener("focus",()=>{targetCell=[r,c];});
    if(name && assets[name]) {
      const img=document.createElement("img");img.src=assetURL(name);img.alt=name.split("/").pop();img.draggable=true;
      img.addEventListener("dragstart",ev=>ev.dataTransfer.setData("text/x-gridfig",JSON.stringify({kind:"grid",r,c})));
      const badge=document.createElement("span");badge.className="cell-index";badge.textContent=`${r+1}.${c+1}`;
      const remove=document.createElement("button");remove.className="remove";remove.textContent="↙";remove.title="Move image to tray";
      remove.addEventListener("click",ev=>{ev.stopPropagation();applyImages(M.moveImage(config,{kind:"grid",r,c},{kind:"tray"}));});
      cell.append(img,badge,remove);
    } else {
      const empty=document.createElement("div");empty.className="empty";
      const plus=document.createElement("span");plus.textContent="+";
      empty.append(plus,document.createTextNode("Choose image"));cell.append(empty);
    }
    cell.addEventListener("click",()=>{targetCell=[r,c];fileDestination="grid";$("files").multiple=false;$("files").click();});
    cell.addEventListener("keydown",ev=>{if(ev.target===cell && (ev.key==="Enter"||ev.key===" ")){ev.preventDefault();cell.click();}});
    cell.addEventListener("dragover",ev=>{ev.preventDefault();cell.classList.add("dragover");});
    cell.addEventListener("dragleave",()=>cell.classList.remove("dragover"));
    cell.addEventListener("drop",async ev=>{
      ev.preventDefault();ev.stopPropagation();cell.classList.remove("dragover");
      try {
        const origin=ev.dataTransfer.getData("text/x-gridfig");
        if(origin)applyImages(M.moveImage(config,dragSource(origin),{kind:"grid",r,c}));
        else await addFiles(ev.dataTransfer.files,[r,c]);
      }catch(e){error(e.message);}
    });
    grid.append(cell);
  }));
  drawTray();pruneAssets();applyLayout();
}
function load(project) {
  const next=project.config;
  if(!next || next.version!==1 || !Array.isArray(next.images) || !next.images.length || !Array.isArray(next.images[0]) || !next.images[0].length)throw Error("Choose a Gridfig project saved by this editor.");
  const nr=next.images.length,nc=next.images[0].length;
  if(nr>20||nc>20||nr*nc>100||!next.images.every(row=>Array.isArray(row)&&row.length===nc))throw Error("Invalid grid dimensions (maximum 100 cells).");
  const incoming=project.assets||{};
  const tray=next.tray ?? [];
  if(!Array.isArray(tray)||tray.length>200||new Set(tray).size!==tray.length)throw Error("Invalid image tray (maximum 200 unused images).");
  for(const path of [...next.images.flat().filter(Boolean),...tray]) {
    if(typeof path!=="string"||!incoming[path]||!/^images\/.+\.(png|jpe?g|svg|webp|gif)$/i.test(path)||path.split("/").includes(".."))throw Error("Project contains an invalid or missing image.");
    atob(incoming[path]);
  }
  const headers=next.headers||{};
  for(const side of sides) {
    const values=headers[side];
    if(values!=null&&(!Array.isArray(values)||values.length!==(side==="top"||side==="bottom"?nc:nr)))throw Error(`Invalid ${side} headers.`);
    if(values?.some(v=>typeof v!=="string"&&!(v&&typeof v.typst==="string")))throw Error("Invalid header label.");
  }
  for(const url of urls.values())URL.revokeObjectURL(url);urls.clear();
  config=structuredClone(next);assets=incoming;config.headers=structuredClone(headers);
  config.tray=M.normalizeTray(config.images,tray);
  config.layout={...defaults,...config.layout,rotations:{...(config.layout?.rotations||{})}};
  config.export={compression:"lossless",jpeg_quality:90,...config.export};
  config.editor={length_unit:"mm",type_unit:"pt",zoom:"1",...config.editor};
  $("length-unit").value=M.mmPerUnit[config.editor.length_unit]?config.editor.length_unit:"mm";
  $("type-unit").value=M.mmPerUnit[config.editor.type_unit]?config.editor.type_unit:"pt";
  $("zoom").value=["fit","0.5","0.75","1","1.5","2"].includes(config.editor.zoom)?config.editor.zoom:"1";
  $("rows").value=nr;$("cols").value=nc;updateUnitControls();
  for(const side of sides){
    const count=side==="top"||side==="bottom"?nc:nr;
    labels[side]=config.headers[side]||Array.from({length:count},(_,i)=>`${side==="top"||side==="bottom"?"Column":"Row"} ${i+1}`);
    $("side-"+side).checked=Array.isArray(config.headers[side]);
    $("rotation-"+side).value=config.layout.rotations[side]||0;
  }
  $("compression").value=config.export.compression;$("jpeg_quality").value=config.export.jpeg_quality;encodingControls();
  targetCell=null;changed();draw();view("edit");error("");
}
function payload(includeTray=true) {
  syncHeaders();
  const snapshot=structuredClone(config);if(!includeTray)delete snapshot.tray;
  const used={};for(const path of [...snapshot.images.flat().filter(Boolean),...(snapshot.tray||[])])used[path]=assets[path];
  return {config:snapshot,assets:used};
}
function download(data,name,type) {
  const url=URL.createObjectURL(new Blob([data],{type})),a=document.createElement("a");
  a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),10000);
}
async function request(route,data) {
  const body=JSON.stringify(data);
  if(new Blob([body]).size>80*1024*1024)throw Error("Project exceeds the 80 MB editor request limit. Use smaller batches or build a config with the CLI.");
  const response=await fetch(route,{method:"POST",headers:{"Content-Type":"application/json"},body});
  const result=await response.json();if(!response.ok)throw Error(result.error||"Rendering failed.");return result;
}
async function run(action) {
  if(busy){if(action==="preview")pendingPreview=true;return;}
  busy=true;error("");const before=revision;
  if(action==="preview"){
    clearTimeout(previewTimer);previewTimer=null;pendingPreview=false;
    view("preview");previewPending();
  }
  const snapshot=payload(action==="bundle"),widthMm=M.geometry(snapshot.config).width;
  for(const id of ["render","export","bundle"])$(id).disabled=true;
  $("status").textContent="Typst is preparing your figure…";
  try {
    const result=await request(action==="preview"?"api/render":"api/export",snapshot);
    if(action==="preview"){
      // A slow response must never replace a more recent edit's preview.
      if(before!==revision){pendingPreview=!$("preview-pane").hidden;return;}
      $("preview").src="data:image/png;base64,"+result.preview;$("preview-empty").hidden=true;
      lastPreview=before;renderedWidthMm=widthMm;applyLayout();
      $("preview-state").hidden=true;$("preview").classList.remove("outdated");
    }
    else if(action==="pdf")download(bytes(result.pdf),"figure.pdf","application/pdf");
    else download(bytes(result.project),"gridfig-project.zip","application/zip");
    $("status").textContent=revision!==before?"Rendered an earlier version · update for your latest edits":action==="preview"?"PDF preview up to date · "+config.export.compression+" raster encoding":"Export ready · original files remain in your editable project";
    if(result.warning)error(result.warning);
  }catch(e){
    if(before===revision || action!=="preview"){
      error(e.message);$("status").textContent="Please check the message below.";
      if(action==="preview")previewPending("Preview could not update. Check the error below.");
    }
  }
  finally{
    busy=false;for(const id of ["render","export","bundle"])$(id).disabled=false;
    if(pendingPreview && !$("preview-pane").hidden && lastPreview!==revision)queuePreview();
  }
}
function imageFiles(files) {
  return Array.from(files).flatMap(file=>{
    if(/\.(png|jpe?g|svg|webp|gif)$/i.test(file.name))return [file];
    const ext={"image/png":"png","image/jpeg":"jpg","image/webp":"webp","image/gif":"gif","image/svg+xml":"svg"}[file.type];
    return ext?[new File([file],"pasted."+ext,{type:file.type})]:[];
  });
}
async function readUploads(files) {
  const result={paths:[],additions:{}};
  for(const file of files) {
    if(file.size>30*1024*1024)throw Error(`${file.name} exceeds the 30 MB image limit.`);
    const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(",")[1]);reader.onerror=()=>reject(Error("Cannot read "+file.name));reader.readAsDataURL(file);});
    const safe=file.name.replace(/[^a-zA-Z0-9._-]/g,"_"),name="images/"+crypto.randomUUID()+"-"+safe;
    result.paths.push(name);result.additions[name]=data;
  }
  const used=new Set([...config.images.flat().filter(Boolean),...config.tray]);
  const existing=[...used].reduce((n,path)=>n+(assets[path]?.length||0),0);
  if(existing+Object.values(result.additions).reduce((n,data)=>n+data.length,0)>78*1024*1024)throw Error("Images exceed the editor's request limit. Import fewer images or use the CLI.");
  return result;
}
async function addFiles(files,cell=null,onlyTray=false) {
  const accepted=imageFiles(files).sort((a,b)=>M.natural(a.webkitRelativePath||a.name,b.webkitRelativePath||b.name));
  if(!accepted.length)throw Error("Choose PNG, JPEG, SVG, WebP or GIF images.");
  const uploaded=await readUploads(accepted),next=M.placeImports(config,uploaded.paths,cell,onlyTray);
  const figureChanged=next.images.some((row,r)=>row.some((path,c)=>path!==config.images[r][c]));
  Object.assign(assets,uploaded.additions);applyImages(next,figureChanged,!onlyTray);error("");
  $("status").textContent=`Loaded ${accepted.length} images · ${config.tray.length} unused images in the tray`;
}
async function importFolder(files) {
  const accepted=imageFiles(files).sort((a,b)=>M.natural(a.webkitRelativePath||a.name,b.webkitRelativePath||b.name));
  if(!accepted.length)throw Error("No supported image files in this folder.");
  if($("folder-mode").value==="flat")return addFiles(accepted);
  const plan=M.methodFolderPlan(accepted.map(file=>file.webkitRelativePath||file.name));
  const uploaded=await readUploads(accepted);
  const images=plan.matrix.map(row=>row.map(i=>i===null?null:uploaded.paths[i]));
  const nextTray=M.normalizeTray(images,[...config.tray,...config.images.flat()]);
  Object.assign(assets,uploaded.additions);config.images=images;config.tray=nextTray;
  labels.top=plan.methods;labels.left=plan.samples;
  labels.bottom=plan.methods.map(()=>"");labels.right=plan.samples.map(()=>"");
  for(const side of sides)$("side-"+side).checked=side==="top"||side==="left";
  $("rows").value=plan.samples.length;$("cols").value=plan.methods.length;
  syncHeaders();targetCell=null;changed();draw();view("edit");error("");
  $("status").textContent=`Imported ${plan.methods.length} methods × ${plan.samples.length} samples · ${plan.matrix.flat().filter(v=>v===null).length} empty cells`;
}
function encodingControls() {
  const lossy=$("compression").value==="jpeg";$("quality-field").hidden=!lossy;
  const notes={
    jpeg:"Re-encode with Pillow, without resizing. Lossy even at 100; transparency becomes white. SVG stays vector.",
    preserve:"Pass originals to Typst without re-encoding. No Pillow needed. JPEG normally keeps its encoding. SVG stays vector.",
    lossless:"Preserve decoded pixels without resizing; cannot restore lost JPEG/WebP detail. Non-PNG rasters need Pillow. SVG stays vector."
  };
  $("encoding-note").textContent=notes[$("compression").value];
}
for(const side of sides) {
  const label=document.createElement("label");label.textContent=side[0].toUpperCase()+side.slice(1)+" · degrees";
  const input=document.createElement("input");input.type="number";input.min=-360;input.max=360;input.step=90;input.value=0;input.id="rotation-"+side;
  input.addEventListener("input",()=>{config.layout.rotations[side]=Number(input.value);changed();});label.append(input);$("rotations").append(label);
  $("side-"+side).addEventListener("change",()=>{syncHeaders();changed();draw();});
}
for(const key of layoutKeys) {
  const input=$(key);input.dataset.baseMin=input.min;input.dataset.baseMax=input.max;
  input.addEventListener("input",()=>{config.layout[key]=nullable(key)&&input.value===""?null:input.type==="number"?fromDisplay(key,Number(input.value)):input.value;changed();});
}
$("preset").onchange=()=>{
  if($("preset").value==="custom")return;
  config.layout=M.presetLayout(config.layout,$("preset").value);
  updateUnitControls();changed();
};
for(const key of ["length","type"])$(key+"-unit").addEventListener("change",()=>{config.editor[key+"_unit"]=$(key+"-unit").value;updateUnitControls();applyLayout();dirty=true;});
$("zoom").onchange=()=>{config.editor.zoom=$("zoom").value;applyLayout();dirty=true;};
$("compression").onchange=()=>{config.export.compression=$("compression").value;encodingControls();changed();};
$("jpeg_quality").oninput=()=>{config.export.jpeg_quality=Number($("jpeg_quality").value);changed();};
for(const id of ["rows","cols"])$(id).addEventListener("change",()=>{
  const nr=Number($("rows").value),nc=Number($("cols").value);
  if(!Number.isInteger(nr)||!Number.isInteger(nc)||nr<1||nc<1||nr>20||nc>20||nr*nc>100){error("Choose 1–20 rows and columns, with at most 100 cells.");$("rows").value=config.images.length;$("cols").value=config.images[0].length;return;}
  const images=Array.from({length:nr},(_,r)=>Array.from({length:nc},(_,c)=>config.images[r]?.[c]||null));
  try{config.tray=M.normalizeTray(images,[...config.tray,...config.images.flat()]);}catch(e){error(e.message);$("rows").value=config.images.length;$("cols").value=config.images[0].length;return;}
  config.images=images;
  for(const side of sides){const count=side==="top"||side==="bottom"?nc:nr;labels[side]=Array.from({length:count},(_,i)=>labels[side][i]||"");}
  syncHeaders();targetCell=null;changed();draw();error("");
});
$("edit-tab").onclick=()=>view("edit");$("preview-tab").onclick=()=>{if(lastPreview!==revision)run("preview");else view("preview");};
$("render").onclick=()=>run("preview");$("export").onclick=()=>run("pdf");$("bundle").onclick=()=>run("bundle");
$("add").onclick=()=>{targetCell=null;fileDestination="grid";$("files").multiple=true;$("files").click();};
$("add-tray").onclick=()=>{fileDestination="tray";$("files").multiple=true;$("files").click();};
$("files").onchange=async()=>{try{await addFiles($("files").files,fileDestination==="tray"?null:targetCell,fileDestination==="tray");}catch(e){error(e.message);}$("files").value="";};
$("folder").onclick=()=>$("folder-files").click();
$("folder-files").onchange=async()=>{try{await importFolder($("folder-files").files);}catch(e){error(e.message);}$("folder-files").value="";};
$("reset").onclick=()=>{targetCell=null;error("");applyImages(M.clearImages(config));};
$("grid-to-tray").onclick=()=>{try{targetCell=null;error("");applyImages(M.gridToTray(config));}catch(e){error(e.message);}};
$("save").onclick=()=>{download(JSON.stringify({format:"gridfig-editor",...payload()},null,2),"figure.gridfig.json","application/json");dirty=false;$("status").textContent="Editable project saved · open this JSON file here to continue later";};
$("open").onclick=()=>$("project-file").click();
$("project-file").onchange=async()=>{try{const file=$("project-file").files[0];if(file){if(file.size>80*1024*1024)throw Error("Project exceeds 80 MB.");load(JSON.parse(await file.text()));dirty=false;}}catch(e){error(e.message);}$("project-file").value="";};
async function demo(){try{const response=await fetch("api/demo");if(!response.ok)throw Error("Could not load the starting project.");load(await response.json());dirty=false;$("status").textContent="Project loaded · layout changes update the arrangement immediately";}catch(e){error(e.message);}}
$("demo").onclick=demo;
document.addEventListener("paste",async ev=>{
  if(ev.target.closest("input,textarea,[contenteditable=true]"))return;
  const files=Array.from(ev.clipboardData?.items||[]).filter(item=>item.kind==="file").map(item=>item.getAsFile()).filter(Boolean);
  if(files.length){ev.preventDefault();try{await addFiles(files,targetCell);}catch(e){error(e.message);}}
});
$("paste").onclick=async()=>{
  try{
    if(!navigator.clipboard?.read)throw Error("Focus a cell, then press Ctrl+V (or ⌘V) to paste an image.");
    const items=await navigator.clipboard.read(),files=[];
    for(const item of items){const type=item.types.find(t=>["image/png","image/jpeg","image/webp"].includes(t));if(type)files.push(new File([await item.getType(type)],"pasted."+({"image/jpeg":"jpg","image/png":"png","image/webp":"webp"}[type]),{type}));}
    if(!files.length)throw Error("No image in the clipboard. Copy image data, then paste; copying a file path is not an image.");
    await addFiles(files,targetCell);
  }catch(e){error(e.name==="NotAllowedError"?"Clipboard access was unavailable. Focus a cell and press Ctrl+V (or ⌘V).":e.message);}
};
const canvas=document.querySelector(".canvas");
$("tray-list").ondragover=ev=>{ev.preventDefault();$("tray-list").classList.add("dragover");};
$("tray-list").ondragleave=()=>$("tray-list").classList.remove("dragover");
$("tray-list").ondrop=ev=>trayDrop(ev);
canvas.addEventListener("dragover",ev=>ev.preventDefault());
canvas.addEventListener("drop",async ev=>{ev.preventDefault();if(ev.dataTransfer.files.length)try{await addFiles(ev.dataTransfer.files);}catch(e){error(e.message);}});
window.addEventListener("beforeunload",ev=>{if(dirty){ev.preventDefault();ev.returnValue="";}});
new ResizeObserver(()=>applyLayout()).observe(canvas);
demo();
