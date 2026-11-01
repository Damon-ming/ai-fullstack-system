export interface UploadFileResult {
  filename: string;
  file_uid: string;
}

export interface UploadFailedFile {
  filename: string;
  error: string;
}

export interface UploadResponse {
  server_time: string;
  files: UploadFileResult[];
  failed_files: UploadFailedFile[];
}
