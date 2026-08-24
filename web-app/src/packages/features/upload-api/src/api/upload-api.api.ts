import { uploadFiles as uploadFilesInFeature } from "@ming/features-upload"

export function uploadFiles(files: File[]) {
  return uploadFilesInFeature(files)
}
