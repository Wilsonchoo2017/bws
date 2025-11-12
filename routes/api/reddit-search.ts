import { FreshContext } from "$fresh/server.ts";
import { db } from "../../db/client.ts";
import { redditSearchResults } from "../../db/schema.ts";

interface RedditPost {
  id: string;
  title: string;
  author: string;
  score: number;
  num_comments: number;
  url: string;
  permalink: string;
  created_utc: number;
  selftext?: string;
}

interface RedditSearchResponse {
  kind: string;
  data: {
    children: Array<{
      kind: string;
      data: RedditPost;
    }>;
    after: string | null;
  };
}

async function searchReddit(
  setNumber: string,
  subreddit = "lego",
): Promise<RedditPost[]> {
  const searchUrl = `https://www.reddit.com/r/${subreddit}/search.json?q=${
    encodeURIComponent(setNumber)
  }&restrict_sr=on&limit=100&sort=relevance`;

  const headers = {
    "User-Agent":
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
  };

  const response = await fetch(searchUrl, { headers });

  if (!response.ok) {
    throw new Error(`Reddit API error: ${response.statusText}`);
  }

  const data: RedditSearchResponse = await response.json();

  return data.data.children.map((child) => ({
    id: child.data.id,
    title: child.data.title,
    author: child.data.author,
    score: child.data.score,
    num_comments: child.data.num_comments,
    url: child.data.url,
    permalink: `https://reddit.com${child.data.permalink}`,
    created_utc: child.data.created_utc,
    selftext: child.data.selftext || undefined,
  }));
}

export const handler = async (
  req: Request,
  _ctx: FreshContext,
): Promise<Response> => {
  try {
    const url = new URL(req.url);
    const setNumber = url.searchParams.get("set");
    const subreddit = url.searchParams.get("subreddit") || "lego";
    const saveToDb = url.searchParams.get("save") === "true";

    if (!setNumber) {
      return new Response(
        JSON.stringify({ error: "Missing 'set' query parameter" }),
        {
          status: 400,
          headers: { "Content-Type": "application/json" },
        },
      );
    }

    // Search Reddit
    const posts = await searchReddit(setNumber, subreddit);

    const result = {
      set_number: setNumber,
      subreddit,
      total_posts: posts.length,
      posts,
    };

    // Optionally save to database
    if (saveToDb) {
      try {
        await db.insert(redditSearchResults).values({
          legoSetNumber: setNumber,
          subreddit,
          totalPosts: posts.length,
          posts: posts as unknown as Record<string, unknown>,
        });

        return new Response(
          JSON.stringify({ ...result, saved: true }, null, 2),
          {
            headers: { "Content-Type": "application/json" },
          },
        );
      } catch (dbError) {
        console.error("Database error:", dbError);
        return new Response(
          JSON.stringify(
            {
              ...result,
              saved: false,
              db_error: dbError instanceof Error
                ? dbError.message
                : "Unknown database error",
            },
            null,
            2,
          ),
          {
            headers: { "Content-Type": "application/json" },
          },
        );
      }
    }

    return new Response(JSON.stringify(result, null, 2), {
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    return new Response(
      JSON.stringify({
        error: error instanceof Error ? error.message : "Unknown error",
      }),
      {
        status: 500,
        headers: { "Content-Type": "application/json" },
      },
    );
  }
};
