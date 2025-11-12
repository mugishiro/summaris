import { z } from 'zod';

const importanceSchema = z.enum(['high', 'medium', 'low']);
const detailStatusSchema = z
  .enum(['partial', 'pending', 'ready', 'stale', 'failed'])
  .nullish()
  .transform((value) => (value ?? undefined));
const optionalStringSchema = z
  .string()
  .trim()
  .min(1)
  .nullish()
  .transform((value) => (value ?? undefined));

const languageArraySchema = z
  .array(z.string().min(1))
  .nullish()
  .transform((value) => (value && value.length > 0 ? value : undefined));

const summaryLongSchema = z
  .string()
  .optional()
  .nullable()
  .transform((value) => (typeof value === 'string' ? value : undefined));

export const clusterSummarySchema = z.object({
  id: z.string().min(1),
  headline: z.string().min(1),
  headlineJa: z.string().optional().nullable(),
  summaryLong: summaryLongSchema,
  createdAt: optionalStringSchema,
  updatedAt: z.string().min(1),
  publishedAt: optionalStringSchema,
  importance: importanceSchema,
  topics: z.array(z.string()),
  languages: languageArraySchema,
  detailStatus: detailStatusSchema,
  detailRequestedAt: optionalStringSchema,
  detailReadyAt: optionalStringSchema,
  detailExpiresAt: optionalStringSchema,
  detailFailedAt: optionalStringSchema,
  detailFailureReason: optionalStringSchema,
  sources: z.array(
    z.object({
      id: z.string().min(1),
      name: z.string().min(1),
      url: z.string().optional().nullable(),
      articleUrl: optionalStringSchema,
      articleTitle: optionalStringSchema,
      siteUrl: optionalStringSchema,
    })
  ),
});

export type ClusterSummarySchema = z.infer<typeof clusterSummarySchema>;

export const clusterListResponseSchema = z.union([
  z.object({
    clusters: z.array(clusterSummarySchema),
  }),
  z.array(clusterSummarySchema),
]);

export const clusterDetailResponseSchema = z.union([
  z.object({
    cluster: clusterSummarySchema.nullish(),
  }),
  z.object({
    data: clusterSummarySchema.nullish(),
  }),
  clusterSummarySchema,
]);
