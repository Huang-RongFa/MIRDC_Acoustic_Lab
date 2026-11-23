import './segmentViewer.css';

const base=(import.meta as ImportMeta & {env:Record<string,string>}).env.BASE_URL;

/** GitHub Pages only: the static segment viewer built by scripts/build_segment_viewer.py into /msm/. */
export function SegmentViewer(){
  return <section className="segment-viewer"><iframe title="切段驗證頁" src={`${base}msm/index.html`}/></section>;
}
