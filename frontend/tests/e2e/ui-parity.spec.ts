import {test,expect} from "@playwright/test";
import {mkdirSync,readFileSync,writeFileSync} from "node:fs";
import path from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
import {PNG} from "pngjs";

const workspaceIds=["project","story","voice","assets","storyboard","delivery"];
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"../../..");
const mockPath=path.join(root,"ui/mockups/index.html");
const out=path.join(root,"frontend/.artifacts/ui-parity");
const expectedBackground="rgb(22, 26, 29)";
function comparePngFiles(a:string,b:string,dest:string){
  const lhs=PNG.sync.read(readFileSync(a)),rhs=PNG.sync.read(readFileSync(b));
  if(lhs.width!==rhs.width||lhs.height!==rhs.height)throw Error("Paired screenshots have different viewports");
  const diff=new PNG({width:lhs.width,height:lhs.height});
  let count=0;
  for(let i=0;i<lhs.data.length;i+=4){
    let different=false;
    for(let k=0;k<3;k++)if(Math.abs(lhs.data[i+k]-rhs.data[i+k])>18)different=true;
    if(different)count++;
    const tone=different?195:34;
    diff.data[i]=tone;diff.data[i+1]=different?88:34;
    diff.data[i+2]=different?75:34;diff.data[i+3]=255;
  }
  writeFileSync(dest,PNG.sync.write(diff));
  return count/(lhs.width*lhs.height);
}

for(const size of [{width:1366,height:768},{width:1920,height:1080}]){
  test("ui-parity real app and immutable mockup "+size.width+"x"+size.height,async({browser})=>{
    mkdirSync(out,{recursive:true});
    const context=await browser.newContext({viewport:size,deviceScaleFactor:1});
    const mock=await context.newPage();
    const real=await context.newPage();
    try{
      await mock.goto(pathToFileURL(mockPath).toString());
      await real.goto("/");
      await real.locator("#new-title").fill("UI parity real local project "+size.width);
      await real.getByRole("button",{name:"Create project"}).click();
      await expect(real.locator(".gateboard .gate")).toHaveCount(5);
      await expect(real.locator(".sidebar nav button")).toHaveCount(6);
      const shell=await real.locator(".sidebar").boundingBox();
      expect(shell).toBeTruthy();
      expect(Math.abs((shell?.width??0)-238)).toBeLessThanOrEqual(3);
      expect(await real.locator("body").evaluate(e=>getComputedStyle(e).backgroundColor)).toBe(expectedBackground);
      const results=[];
      for(let i=0;i<workspaceIds.length;i++){
        const id=workspaceIds[i];
        await mock.locator(`button[data-tab="${id}"]`).click();
        await real.locator(".sidebar nav button").nth(i).click();
        await expect(real.locator(".content").first()).toBeVisible();
        await expect(real.locator(".sidebar nav button").nth(i)).toHaveAttribute("aria-current","page");
        const overflow=await real.evaluate(()=>{
          const doc=document.documentElement;
          return {scrollWidth:doc.scrollWidth,innerWidth:innerWidth};
        });
        expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.innerWidth+2);
        const prefix=`${id}-${size.width}x${size.height}`;
        const a=path.join(out,prefix+"-mock.png"),b=path.join(out,prefix+"-production.png");
        const diff=path.join(out,prefix+"-difference.png");
        await mock.screenshot({path:a,animations:"disabled"});
        await real.screenshot({path:b,animations:"disabled"});
        const divergentPixelFraction=comparePngFiles(a,b,diff);
        results.push({workspace:id,viewport:size,dpr:1,shell_width_px:shell?.width,
          no_horizontal_overflow:true,divergentPixelFraction,
          screenshots:[path.basename(a),path.basename(b),path.basename(diff)],
          dynamic_content_comparable:false,
          note:"Mock is a static fictitious fixture. Production shows an actual new SQLite project with authentic blocked G1–G5 states; screenshots are structural, not identical content."});
      }
      writeFileSync(path.join(out,`ledger-${size.width}x${size.height}.json`),
        JSON.stringify({source:"approved unchanged static mockup / real React application",
          viewports:results,results_kind:"VISUAL_STRUCTURE_ONLY_NOT_FULL_FLOW"},null,2));
    }finally{
      await context.close();
    }
  });
}
