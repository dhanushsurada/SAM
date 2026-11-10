export interface Base64Payload {
  data: string;
  mimeType: string;
}

/** Reads a Blob (or File) as base64, stripping the "data:mime;base64,"
 * prefix — the server (multimodal/media_validation.py) expects raw base64
 * only. */
export function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      const commaIndex = result.indexOf(",");
      resolve(commaIndex >= 0 ? result.slice(commaIndex + 1) : result);
    };
    reader.onerror = () => reject(reader.error ?? new Error("Failed to read file"));
    reader.readAsDataURL(blob);
  });
}

export async function fileToBase64Payload(file: File): Promise<Base64Payload> {
  return { data: await blobToBase64(file), mimeType: file.type };
}
