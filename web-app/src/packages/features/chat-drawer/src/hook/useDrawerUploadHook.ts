import { uploadFiles as uploadFilesFromApi } from "@ming/features-upload-api";
import { useChatUploadStore } from "@ming/store/biz/upload-state";

export function useDrawerUploadHook() {
  const upload = useChatUploadStore((s) => s.upload);
  const startUpload = useChatUploadStore((s) => s.startUpload);
  const finishUpload = useChatUploadStore((s) => s.finishUpload);

  const handleUpload = async (fileList?: FileList | null) => {
    const files = fileList ? Array.from(fileList) : [];
    if (!files.length) return;
    startUpload(files.map((file) => file.name));
    const [err, response] = await uploadFilesFromApi(files);
    if (err) {
      finishUpload("error", err.clientData?.message || "文件上传失败");
    } else {
      const resultFiles = Array.isArray(response?.data?.files)
        ? response.data.files
        : [];
      const allIndexed =
        resultFiles.length === 0 ||
        resultFiles.every((file) => file.indexed || file.duplicate);
      finishUpload(
        "success",
        allIndexed ? "文件已经进入语料库" : "文件已上传，部分词条仍在更新",
        resultFiles,
      );
    }
  };

  return { upload, handleUpload };
}
