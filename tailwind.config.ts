import { type Config } from "tailwindcss";
// @ts-ignore: DaisyUI types are not fully compatible
import daisyui from "daisyui";

export default {
  content: [
    "{routes,islands,components}/**/*.{ts,tsx}",
  ],
  // @ts-ignore: DaisyUI types are not fully compatible
  plugins: [daisyui],
} satisfies Config;
