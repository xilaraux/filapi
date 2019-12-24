drop table if exists files;

create table files (
  name text not null,
  hash text not null primary key,
  size integer
);
