import { useRef, useState } from 'react';

interface ImageUploaderProps {
  onImageSelected: (base64: string, mimeType: string, preview: string) => void;
}

const MAX_SIZE_MB = 10;
const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

export default function ImageUploader({ onImageSelected }: ImageUploaderProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFile = (file: File) => {
    setError(null);

    if (!ALLOWED_TYPES.includes(file.type)) {
      setError('JPG, PNG, WEBP 형식만 지원해요');
      return;
    }

    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      setError(`${MAX_SIZE_MB}MB 이하 파일만 업로드할 수 있어요`);
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      const dataUrl = e.target?.result as string;
      // base64 부분만 추출 (data:image/jpeg;base64, 제거)
      const base64 = dataUrl.split(',')[1];
      onImageSelected(base64, file.type, dataUrl);
    };
    reader.readAsDataURL(file);
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    e.target.value = ''; // 동일 파일 재선택 허용
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  };

  return (
    <div>
      <button
        onClick={() => inputRef.current?.click()}
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
        style={{
          width: '100%',
          height: 200,
          border: '2px dashed #C5CDD4',
          borderRadius: 16,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 12,
          background: '#F9FAFB',
          cursor: 'pointer',
          transition: 'border-color 0.15s, background 0.15s',
        }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLButtonElement).style.borderColor = '#0064FF';
          (e.currentTarget as HTMLButtonElement).style.background = '#F0F4FF';
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLButtonElement).style.borderColor = '#C5CDD4';
          (e.currentTarget as HTMLButtonElement).style.background = '#F9FAFB';
        }}
      >
        <span style={{ fontSize: 40 }}>👗</span>
        <div style={{ textAlign: 'center' }}>
          <p style={{ fontSize: 15, fontWeight: 600, color: '#191F28' }}>
            사진 선택하기
          </p>
          <p style={{ fontSize: 13, color: '#778088', marginTop: 4 }}>
            갤러리에서 옷 사진을 선택하세요
          </p>
          <p style={{ fontSize: 12, color: '#C5CDD4', marginTop: 4 }}>
            JPG · PNG · WEBP · 최대 10MB
          </p>
        </div>
      </button>

      {error && (
        <p style={{ fontSize: 13, color: '#F04452', marginTop: 8, textAlign: 'center' }}>
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
