package sample

import "fmt"

type UserService struct {
	Name  string
	Email string
	Age   int
}

type Validator interface {
	Validate() error
	IsValid() bool
}

func NewUserService(name, email string) *UserService {
	return &UserService{
		Name:  name,
		Email: email,
	}
}

func (u *UserService) String() string {
	return fmt.Sprintf("%s <%s>", u.Name, u.Email)
}

func FormatAge(age int) string {
	return fmt.Sprintf("%d years old", age)
}
