import { Download, X } from "lucide-react";

interface Props {
  src: string | null;
  title: string;
  downloadUrl?: string;
  onClose: () => void;
}

export default function ImagePreviewModal({ src, title, downloadUrl, onClose }: Props) {
  if (!src) return null;
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="image-modal" onClick={(event) => event.stopPropagation()}>
        <div className="modal-bar">
          <strong>{title}</strong>
          <div>
            {downloadUrl && (
              <a className="icon-button" href={downloadUrl}>
                <Download size={17} />
              </a>
            )}
            <button className="icon-button" onClick={onClose}>
              <X size={18} />
            </button>
          </div>
        </div>
        <img src={src} alt={title} />
      </div>
    </div>
  );
}
