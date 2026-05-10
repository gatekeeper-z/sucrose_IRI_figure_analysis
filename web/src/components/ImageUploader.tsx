import { ImagePlus, X } from "lucide-react";
import { useRef } from "react";

interface Props {
  files: File[];
  onFiles: (files: File[]) => void;
}

export default function ImageUploader({ files, onFiles }: Props) {
  const inputRef = useRef<HTMLInputElement | null>(null);

  function addFiles(list: FileList | null) {
    if (!list) return;
    const next = [...files, ...Array.from(list)];
    onFiles(next);
  }

  function openPicker() {
    inputRef.current?.click();
  }

  return (
    <section className="panel upload-panel">
      <input
        ref={inputRef}
        className="file-input"
        type="file"
        multiple
        accept=".bmp,.png,.jpg,.jpeg,.tif,.tiff"
        onChange={(event) => {
          addFiles(event.target.files);
          event.currentTarget.value = "";
        }}
      />
      <div
        className="drop-zone"
        onClick={openPicker}
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          addFiles(event.dataTransfer.files);
        }}
      >
        <ImagePlus size={36} />
        <button
          className="upload-button"
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            openPicker();
          }}
        >
          选择图片
        </button>
        <span>BMP / PNG / JPG / TIF</span>
      </div>
      {files.length > 0 && (
        <div className="file-list">
          {files.map((file, index) => (
            <div className="file-row" key={`${file.name}-${index}`}>
              <span>{file.name}</span>
              <button className="icon-button" onClick={() => onFiles(files.filter((_, i) => i !== index))}>
                <X size={16} />
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
