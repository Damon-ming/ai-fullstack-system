export interface UploadResponse {
  server_time: string;
  files: Array<{
    filename: string;
    save_path: string;
    file_size: number;
    file_md5: string;
    duplicate: boolean;
    indexed: boolean;
  }>;
}
