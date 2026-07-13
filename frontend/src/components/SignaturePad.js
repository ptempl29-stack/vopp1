import React, { useRef, useEffect, useState } from "react";
import { Eraser, Upload } from "lucide-react";
import { toast } from "sonner";

export const SignaturePad = ({ value, onChange, testid, height = 160, allowUpload = false }) => {
  const canvasRef = useRef(null);
  const drawing = useRef(false);
  const last = useRef([0, 0]);
  const [empty, setEmpty] = useState(!value);

  const draw = (src) => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    const img = new Image();
    img.onload = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    };
    img.src = src;
    setEmpty(false);
  };

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    ctx.lineWidth = 2.2;
    ctx.lineCap = "round";
    ctx.strokeStyle = "#18301F";
    if (value) draw(value);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const point = (e) => {
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const t = e.touches ? e.touches[0] : e;
    return [
      (t.clientX - rect.left) * (canvas.width / rect.width),
      (t.clientY - rect.top) * (canvas.height / rect.height),
    ];
  };

  const start = (e) => { e.preventDefault(); drawing.current = true; last.current = point(e); };
  const move = (e) => {
    if (!drawing.current) return;
    e.preventDefault();
    const ctx = canvasRef.current.getContext("2d");
    const [x, y] = point(e);
    ctx.beginPath();
    ctx.moveTo(last.current[0], last.current[1]);
    ctx.lineTo(x, y);
    ctx.stroke();
    last.current = [x, y];
    setEmpty(false);
  };
  const end = () => {
    if (!drawing.current) return;
    drawing.current = false;
    onChange?.(canvasRef.current.toDataURL("image/png"));
  };

  const clear = () => {
    const canvas = canvasRef.current;
    canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
    setEmpty(true);
    onChange?.("");
  };

  const onUpload = (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    if (!file.type.startsWith("image/")) { toast.error("Please upload an image file"); return; }
    if (file.size > 600 * 1024) { toast.error("Signature image too large (max ~600KB)"); return; }
    const reader = new FileReader();
    reader.onload = () => { draw(reader.result); onChange?.(reader.result); };
    reader.readAsDataURL(file);
  };

  return (
    <div>
      <div className="relative rounded-md border-2 border-dashed border-tan-300 bg-tan-50 overflow-hidden">
        <canvas
          ref={canvasRef}
          width={520}
          height={height}
          data-testid={testid}
          className="w-full touch-none cursor-crosshair"
          style={{ height }}
          onMouseDown={start} onMouseMove={move} onMouseUp={end} onMouseLeave={end}
          onTouchStart={start} onTouchMove={move} onTouchEnd={end}
        />
        {empty && (
          <span className="pointer-events-none absolute inset-0 flex items-center justify-center text-sm text-stone-400">
            Sign here
          </span>
        )}
      </div>
      <div className="mt-2 flex items-center gap-4">
        <button type="button" onClick={clear} data-testid={testid ? `${testid}-clear` : "sig-clear"}
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-stone-500 hover:text-moneygreen-700 transition-colors duration-200">
          <Eraser className="w-3.5 h-3.5" /> Clear
        </button>
        {allowUpload && (
          <label className="inline-flex items-center gap-1.5 text-xs font-semibold text-stone-500 hover:text-moneygreen-700 transition-colors duration-200 cursor-pointer"
            data-testid={testid ? `${testid}-upload-label` : "sig-upload-label"}>
            <Upload className="w-3.5 h-3.5" /> Upload image
            <input type="file" accept="image/*" className="hidden" onChange={onUpload}
              data-testid={testid ? `${testid}-upload` : "sig-upload"} />
          </label>
        )}
      </div>
    </div>
  );
};
