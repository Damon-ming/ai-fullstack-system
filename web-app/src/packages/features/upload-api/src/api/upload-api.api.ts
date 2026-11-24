import { uploadFiles as uploadFilesInFeature } from "@ming/feature-upload";

export { UPLOAD_ACCEPT } from "@ming/feature-upload";

export function uploadFiles(files: File[], signal?: AbortSignal) {
  return uploadFilesInFeature(files, signal);
}
