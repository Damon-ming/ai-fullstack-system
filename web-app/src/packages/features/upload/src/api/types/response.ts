export interface UploadFileResult {
  filename: string;
  file_id: string;
}

export interface UploadDuplicateFile {
  filename: string;
}

export interface UploadFailedFile {
  filename: string;
  error: string;
}

export interface UploadResponse {
  success_files: UploadFileResult[];
  duplicate_files: UploadDuplicateFile[];
  failed_files: UploadFailedFile[];
}
