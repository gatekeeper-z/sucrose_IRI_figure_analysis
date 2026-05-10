import { Download, Maximize2 } from "lucide-react";
import { downloadFileUrl, fileUrl } from "../api";

interface Props {
  jobId: string;
  imageId: string;
  files: string[];
  onPreview: (src: string, title: string, downloadUrl: string) => void;
}

const groups = [
  {
    title: "基础图",
    files: ["00_original.png", "01_gray.png"]
  },
  {
    title: "背景校正",
    files: [
      "02a_gradient_protect_mask_debug.png",
      "02b_candidate_protect_mask.png",
      "02c_square_preflight_overlay.png",
      "03_background_estimate.png",
      "04_flatfield_corrected.png",
      "05_bg_corrected_clahe.png"
    ]
  },
  {
    title: "候选",
    files: [
      "06a_candidate_raw_overlay.png",
      "06b_candidate_accepted_overlay.png",
      "06c_candidate_rejected_overlay.png",
      "06d_square_candidate_overlay.png",
      "06e_shape_accepted_overlay.png",
      "06f_shape_rejected_overlay.png"
    ]
  },
  {
    title: "轮廓和实例",
    files: [
      "07a_radial_reliable_points_overlay.png",
      "07b_radial_rejected_points_overlay.png",
      "07c_contour_refined_overlay.png",
      "07d_square_contour_refined_overlay.png",
      "07e_square_instance_masks.png",
      "07f_cluster_parent_overlay.png",
      "07g_cluster_split_overlay.png",
      "08_instance_masks.png",
      "09_final_mask.png",
      "10_final_overlay.png",
      "11_label_overlay.png",
      "12_area_histogram.png"
    ]
  }
];

const dataFiles = ["crystals.csv", "candidates_accepted.csv", "candidates_rejected.csv", "summary.json", "qc_report.txt"];

export default function ResultGallery({ jobId, imageId, files, onPreview }: Props) {
  const available = new Set(files);
  return (
    <div className="gallery-stack">
      {groups.map((group) => (
        <section className="panel" key={group.title}>
          <div className="panel-title">
            <span>{group.title}</span>
          </div>
          <div className="image-grid">
            {group.files.map((filename) =>
              available.has(filename) ? (
                <ResultTile
                  key={filename}
                  jobId={jobId}
                  imageId={imageId}
                  filename={filename}
                  onPreview={onPreview}
                />
              ) : (
                <div className="result-tile missing" key={filename}>
                  <span>{filename}</span>
                </div>
              )
            )}
          </div>
        </section>
      ))}
      <section className="panel">
        <div className="panel-title">
          <span>数据</span>
        </div>
        <div className="download-grid">
          {dataFiles.filter((file) => available.has(file)).map((file) => (
            <a href={downloadFileUrl(jobId, imageId, file)} key={file}>
              <Download size={16} /> {file}
            </a>
          ))}
        </div>
      </section>
    </div>
  );
}

function ResultTile({
  jobId,
  imageId,
  filename,
  onPreview
}: {
  jobId: string;
  imageId: string;
  filename: string;
  onPreview: (src: string, title: string, downloadUrl: string) => void;
}) {
  const src = fileUrl(jobId, imageId, filename);
  const downloadUrl = downloadFileUrl(jobId, imageId, filename);
  return (
    <div className="result-tile">
      <img src={src} alt={filename} loading="lazy" />
      <div className="tile-actions">
        <span>{filename}</span>
        <button className="icon-button" onClick={() => onPreview(src, filename, downloadUrl)}>
          <Maximize2 size={16} />
        </button>
        <a className="icon-button" href={downloadUrl}>
          <Download size={16} />
        </a>
      </div>
    </div>
  );
}
