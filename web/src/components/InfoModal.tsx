import { Info, X } from "lucide-react";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function InfoModal({ open, onClose }: Props) {
  if (!open) return null;
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section className="info-modal" onClick={(event) => event.stopPropagation()}>
        <div className="modal-bar">
          <div className="info-title">
            <Info size={19} />
            <strong>使用说明</strong>
          </div>
          <button className="icon-button" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <div className="info-content">
          <section>
            <h3>基本方法</h3>
            <p>
              系统用于分析蔗糖法 IRI 显微图像中的冰晶实际轮廓面积。默认流程为灰度化、背景校正、CLAHE 增强、候选定位、实际轮廓恢复、面积统计和 QC 报告。
            </p>
            <p>
              Hough 和 LoG 只用于寻找候选位置，最终面积来自实例 mask 的像素面积，不使用圆面积或矩形面积作为主结果。
            </p>
          </section>

          <section>
            <h3>操作流程</h3>
            <ol>
              <li>在“分析”页选择一张或多张显微图片。</li>
              <li>选择配置预设，必要时调整像素尺寸、方形策略和粘连分裂。</li>
              <li>点击“开始分析”，等待进度完成。</li>
              <li>进入结果页检查 final overlay、label overlay、方形轮廓和粘连分裂图。</li>
              <li>在历史页按处理时间查看过往分析，或下载单图/整批结果。</li>
            </ol>
          </section>

          <section>
            <h3>预设区别</h3>
            <dl>
              <dt>默认</dt>
              <dd>通用参数，适合先试跑和普通圆形冰晶。</dd>
              <dt>0.1 PVA</dt>
              <dd>偏向圆形、分离冰晶，方形策略默认不应误触发。</dd>
              <dt>0.2 PVA</dt>
              <dd>增强方形/短棒状冰晶识别，并允许保守的轻微粘连分裂。</dd>
            </dl>
          </section>

          <section>
            <h3>重要参数</h3>
            <dl>
              <dt>像素尺寸</dt>
              <dd>
                填写 um/px 后可输出 um² 和等效直径 um；留空时只输出 px²。例如显微标定为每像素
                0.5 um，则填写 <code>0.5</code>；不确定标定时保持空白，不要填写单位或文字。
              </dd>
              <dt>排除贴边对象</dt>
              <dd>开启后贴到图像边缘的候选不进入 accepted 科学统计。</dd>
              <dt>方形策略</dt>
              <dd>自动模式会先扫描图像，发现足够多未被圆形候选覆盖的方形候选后才启用；开启为强制使用；关闭则只用圆形流程。</dd>
              <dt>粘连分裂</dt>
              <dd>自动模式只对高置信轻微粘连做分裂。开启会更积极，关闭会避免过度拆分。</dd>
              <dt>背景尺度</dt>
              <dd>数值越大越偏向大尺度阴影校正；过小可能把冰晶边缘带入背景。</dd>
              <dt>保护上限</dt>
              <dd>限制背景估计时被保护区域的最大比例，过高可能保留阴影，过低可能压掉冰晶边缘。</dd>
              <dt>Hough 阈值</dt>
              <dd>降低会增加圆形候选召回，但也会增加噪声候选；提高会更保守。</dd>
              <dt>最小/最大半径</dt>
              <dd>限定候选冰晶尺寸范围，设置过窄会漏检，过宽会引入背景结构。</dd>
              <dt>可靠射线</dt>
              <dd>圆形轮廓恢复所需的可靠边界比例。提高会更严格，降低会保留更多弱边界对象。</dd>
              <dt>方形边界</dt>
              <dd>方形候选边界强度相对局部噪声的要求。降低可增加方形召回，但误检风险更高。</dd>
              <dt>方形支撑</dt>
              <dd>方形轮廓闭合和边界支撑要求。提高会更干净，降低可保留更多断裂边界。</dd>
            </dl>
          </section>

          <section>
            <h3>结果与下载</h3>
            <p>
              结果页展示原图、灰度图、背景估计、候选 overlay、方形候选、径向点、实例 mask、final overlay、label overlay、面积直方图和 QC 报告。
            </p>
            <p>
              可下载单张中间图、单图完整 ZIP，或整批完整 ZIP。核心统计请优先使用 summary 中的 accepted_total_actual_area_px2 和 crystals.csv 中 accepted 为 true 的对象。
            </p>
          </section>
        </div>
      </section>
    </div>
  );
}
