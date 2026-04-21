import { useEffect, useRef, useState } from 'react';

interface ImageUploaderProps {
  onImageSelected: (base64: string, mimeType: string, preview: string) => void;
}

const MAX_SIZE_MB = 10;
const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

function CameraIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
      <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
      <circle cx="12" cy="13" r="4" />
    </svg>
  );
}

export default function ImageUploader({ onImageSelected }: ImageUploaderProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  const handleFile = (file: File) => {
    setError(null);

    if (!ALLOWED_TYPES.includes(file.type)) {
      setError('JPG, PNG, WEBP 파일만 업로드할 수 있어요.');
      return;
    }

    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      setError(`${MAX_SIZE_MB}MB 이하 파일만 업로드할 수 있어요.`);
      return;
    }

    const reader = new FileReader();
    reader.onload = (event) => {
      const dataUrl = event.target?.result as string;
      const base64 = dataUrl.split(',')[1];
      onImageSelected(base64, file.type, dataUrl);
    };
    reader.readAsDataURL(file);
  };

  useEffect(() => {
    const handlePaste = (event: ClipboardEvent) => {
      const items = event.clipboardData?.items;
      if (!items) return;

      for (const item of Array.from(items)) {
        if (!item.type.startsWith('image/')) continue;
        const file = item.getAsFile();
        if (file) handleFile(file);
        break;
      }
    };

    document.addEventListener('paste', handlePaste);
    return () => document.removeEventListener('paste', handlePaste);
  }, []);

  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) handleFile(file);
    event.target.value = '';
  };

  const handleDrop = (event: React.DragEvent<HTMLButtonElement>) => {
    event.preventDefault();
    setIsDragOver(false);
    const file = event.dataTransfer.files?.[0];
    if (file) handleFile(file);
  };

  return (
    <div>
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDrop={handleDrop}
        onDragOver={(event) => {
          event.preventDefault();
          setIsDragOver(true);
        }}
        onDragLeave={() => setIsDragOver(false)}
        className="fade-rise"
        style={{
          width: '100%',
          minHeight: 208,
          padding: '28px 22px',
          borderRadius: 24,
          border: `2px ${isDragOver ? 'solid' : 'dashed'} ${isDragOver ? '#c3849a' : '#e5d8ca'}`,
          background: isDragOver ? 'rgba(241, 217, 227, 0.58)' : 'rgba(255, 250, 244, 0.86)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 14,
          textAlign: 'center',
          transition: 'all 0.18s ease',
        }}
      >
        <div
          style={{
            width: 58,
            height: 58,
            borderRadius: '50%',
            background: '#f1d9e3',
            color: '#aa6d82',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 10px 24px rgba(170, 109, 130, 0.14)',
          }}
        >
          <CameraIcon />
        </div>

        <div>
          <p style={{ fontSize: 16, fontWeight: 600, color: '#2c241f' }}>사진 선택하기</p>
          <p style={{ fontSize: 13, lineHeight: 1.7, color: '#8c7c71', marginTop: 8 }}>
            갤러리에서 착장 사진을 올리거나
            <br />
            이미지를 복사해서 Ctrl+V로 붙여넣을 수 있어요.
          </p>
          <p style={{ fontSize: 12, color: '#b6a89c', marginTop: 8 }}>JPG · PNG · WEBP · 최대 10MB</p>
        </div>
      </button>

      {error && (
        <p style={{ marginTop: 10, textAlign: 'center', fontSize: 13, color: 'var(--cloi-danger)' }}>
          {error}
        </p>
      )}

      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        onChange={handleChange}
        style={{ display: 'none' }}
      />
    </div>
  );
}
