export type DataSourceKind = 'api' | 'dynamodb';

export type DataSourceFailure = {
  source: DataSourceKind;
  message: string;
};

export class ClusterDataError extends Error {
  readonly failures: DataSourceFailure[];

  constructor(message: string, failures: DataSourceFailure[]) {
    super(message);
    this.name = 'ClusterDataError';
    this.failures = failures;
  }
}
