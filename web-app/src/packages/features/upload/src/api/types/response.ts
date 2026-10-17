export interface UploadResponse {
  server_time: string;
  files: Array<{
    filename: string;
    save_path: string;
    file_size: number;
    file_sha256: string;
    duplicate: boolean;
    indexed: boolean;
  }>;
}
