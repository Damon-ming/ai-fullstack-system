import { uploadFiles as uploadFilesInFeature } from "@ming/features-upload"

export function uploadFiles(files: File[], signal?: AbortSignal) {
  return uploadFilesInFeature(files, undefined, signal)
}
