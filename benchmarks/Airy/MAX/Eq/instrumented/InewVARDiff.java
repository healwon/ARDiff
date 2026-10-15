package demo.benchmarks.Airy.MAX.Eq.instrumented;
import equiv.checking.symbex.UnInterpreted;
public class InewVARDiff{
    public static double snippet(double a, double b) {
        if (b < a)//change
            return a;//change
        else
            return b;//change
    }
public static void main(String[] args){
InewVARDiff temp = new InewVARDiff();
temp.snippet(1,1);
}
}
