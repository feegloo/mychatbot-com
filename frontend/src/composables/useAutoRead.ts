import { ref, watch, type Ref } from "vue";
import { synthesizeSpeech } from "../api";
import { getData, setData } from "../utils/localData";

const AUTO_READ_KEY = "autoReadEnabled";

/**
 * Composable that provides auto-read (TTS) functionality.
 *
 * When enabled, assistant messages are synthesized paragraph-by-paragraph
 * and played sequentially. The setting persists in localStorage.
 */
export function useAutoRead(
  messages: Ref<{ role: string; content: string }[]>,
  asking: Ref<boolean>,
  welcomeMessage?: Ref<string>,
) {
  const enabled = ref(getData<boolean>(AUTO_READ_KEY) ?? false);

  let currentAudio: HTMLAudioElement | null = null;
  let currentBlobUrl: string | null = null;
  let aborted = false;

  function toggle() {
    enabled.value = !enabled.value;
    setData(AUTO_READ_KEY, enabled.value);
    if (!enabled.value) {
      stop();
    }
  }

  function stop() {
    aborted = true;
    if (currentAudio) {
      currentAudio.pause();
      currentAudio = null;
    }
    if (currentBlobUrl) {
      URL.revokeObjectURL(currentBlobUrl);
      currentBlobUrl = null;
    }
  }

  function splitIntoParagraphs(text: string): string[] {
    // Strip markdown images, HTML tags, and error markers
    const cleaned = text
      .replace(/!\[.*?\]\(.*?\)/g, "")
      .replace(/<[^>]+>/g, "")
      .replace(/⚠️/g, "");

    return cleaned
      .split(/\n{2,}/)
      .map((p) => p.trim())
      .filter((p) => p.length > 0 && p.length < 2000);
  }

  async function playParagraph(text: string): Promise<void> {
    if (aborted) return;
    const blob = await synthesizeSpeech(text);
    if (aborted) return;
    const url = URL.createObjectURL(blob);
    currentBlobUrl = url;

    return new Promise<void>((resolve) => {
      const audio = new Audio(url);
      currentAudio = audio;
      audio.addEventListener("ended", () => {
        URL.revokeObjectURL(url);
        currentBlobUrl = null;
        currentAudio = null;
        resolve();
      });
      audio.addEventListener("error", () => {
        URL.revokeObjectURL(url);
        currentBlobUrl = null;
        currentAudio = null;
        resolve();
      });
      audio.play().catch(() => resolve());
    });
  }

  async function readAloud(text: string) {
    stop();
    aborted = false;
    const paragraphs = splitIntoParagraphs(text);
    for (const paragraph of paragraphs) {
      if (aborted) break;
      await playParagraph(paragraph);
    }
  }

  /** Read the last assistant message when `asking` transitions from true→false */
  let prevAsking = asking.value;
  watch(asking, (newVal) => {
    if (prevAsking && !newVal && enabled.value) {
      const lastMsg = [...messages.value].reverse().find((m) => m.role === "assistant");
      if (lastMsg?.content) {
        readAloud(lastMsg.content);
      }
    }
    prevAsking = newVal;
  });

  /** Read the welcome message when it first becomes available and auto-read is on */
  function readWelcomeIfEnabled() {
    if (!enabled.value) return;
    const content = welcomeMessage?.value;
    if (content) {
      readAloud(content);
    }
  }

  function cleanup() {
    stop();
  }

  return { enabled, toggle, stop, readAloud, readWelcomeIfEnabled, cleanup };
}
