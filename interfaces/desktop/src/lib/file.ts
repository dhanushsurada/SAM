export interface Base64Payload {
  data: string;
  mimeType: string;
}

/** Reads a File as base64, stripping the "data:mime;base64," prefix — the
 * server (multimodal/media_validation.py) expects raw base64 only. */
export function fileToBase64Payload(file: File): Promise<Base64Payload> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      const commaIndex = result.indexOf(",");
      resolve({
        data: commaIndex >= 0 ? result.slice(commaIndex + 1) : result,
        mimeType: file.type,
      });
    };
    reader.onerror = () => reject(reader.error ?? new Error("Failed to read file"));
    reader.readAsDataURL(file);
  });
}
